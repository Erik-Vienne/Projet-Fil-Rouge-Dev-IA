import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import mysql.connector
from pypdf import PdfWriter

import agent


def appel_outil(nom, arguments, identifiant):
    return SimpleNamespace(
        id=identifiant,
        function=SimpleNamespace(name=nom, arguments=json.dumps(arguments)),
    )


def reponse_modele(contenu=None, appels=None):
    message = MagicMock()
    message.content = contenu
    message.tool_calls = appels
    message.model_dump.return_value = {
        "role": "assistant",
        "content": contenu,
        "tool_calls": [
            {
                "id": appel.id,
                "type": "function",
                "function": {
                    "name": appel.function.name,
                    "arguments": appel.function.arguments,
                },
            }
            for appel in appels or []
        ],
    }
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class DocumentsTests(unittest.TestCase):
    def test_toutes_les_fiches_reelles_sont_chargees(self):
        morceaux = agent.charger_documents(agent.DOSSIER_FICHES)
        fichiers = {
            str(p.relative_to(agent.DOSSIER_FICHES))
            for p in agent.DOSSIER_FICHES.rglob("*")
            if p.suffix.lower() == ".pdf"
        }
        self.assertEqual({m["document"] for m in morceaux}, fichiers)
        self.assertTrue(all(m["texte"] and m["page"] >= 1 for m in morceaux))
        self.assertEqual(agent.chercher_fiches(morceaux)["nombre_pages"], len(morceaux))
        resultat = agent.chercher_fiches(morceaux, fournisseur="CafeoPro")
        self.assertEqual(len(resultat["resultats"]), 1)
        self.assertIn("FRN-006", resultat["resultats"][0]["document"])

    def test_recherche_normalise_accents_et_ponctuation(self):
        morceaux = [{"document": "fiche.pdf", "page": 2, "texte": "Délai : 3 jours. CaféoPro"}]
        resultat = agent.chercher_fiches(morceaux, "delai ?", "CafeoPro")
        self.assertEqual(resultat["resultats"], morceaux)
        self.assertEqual(agent.chercher_fiches(morceaux, "inexistant")["resultats"], [])

    def test_dossier_absent_ou_vide_signale(self):
        with tempfile.TemporaryDirectory() as dossier:
            for chemin in (Path(dossier), Path(dossier) / "absent"):
                with self.assertRaises(ValueError):
                    agent.charger_documents(chemin)

    def test_scan_sans_texte_signale_meme_dans_sous_dossier(self):
        with tempfile.TemporaryDirectory() as dossier:
            sous_dossier = Path(dossier) / "archives"
            sous_dossier.mkdir()
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.write(sous_dossier / "scan.PDF")
            with self.assertRaisesRegex(ValueError, "OCR"):
                agent.charger_documents(dossier)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.agent = agent.Agent(self.client, "deploiement-test", {}, [])

    def test_sql_parametre_et_filtres_zero(self):
        with patch.object(self.agent, "executer_requete", return_value={}) as executer:
            self.agent.rechercher_produits(
                mot_cle="' OR 1=1 --", categorie="Audio",
                fournisseur="NovaTech", prix_max=0, stock_max=0,
            )
        sql, parametres = executer.call_args.args
        self.assertNotIn("' OR 1=1 --", sql)
        self.assertNotIn("pays", sql)
        self.assertIn("stock <= %s", sql)
        self.assertEqual(parametres, ["%' OR 1=1 --%", "%Audio%", "%NovaTech%", 0, 0])

    def test_statistiques_refuse_colonne_arbitraire(self):
        with self.assertRaises(ValueError):
            self.agent.statistiques("fournisseur; DROP TABLE produits")
        with patch.object(self.agent, "executer_requete") as executer:
            self.agent.statistiques("categorie")
        self.assertIn("GROUP BY categorie", executer.call_args.args[0])

    def test_fermeture_connexion_et_troncature(self):
        connexion = MagicMock()
        curseur = connexion.cursor.return_value
        curseur.fetchmany.return_value = [{"id": i} for i in range(agent.MAX_LIGNES + 1)]
        with patch("agent.mysql.connector.connect", return_value=connexion):
            resultat = self.agent.executer_requete("SELECT id FROM produits")
        self.assertTrue(resultat["tronque"])
        self.assertEqual(len(resultat["resultats"]), agent.MAX_LIGNES)
        curseur.close.assert_called_once()
        connexion.close.assert_called_once()

    def test_fermeture_meme_en_erreur_sql(self):
        connexion = MagicMock()
        curseur = connexion.cursor.return_value
        curseur.execute.side_effect = mysql.connector.Error("indisponible")
        with patch("agent.mysql.connector.connect", return_value=connexion):
            with self.assertRaises(mysql.connector.Error):
                self.agent.executer_requete("SELECT id FROM produits")
        curseur.close.assert_called_once()
        connexion.close.assert_called_once()

    def test_arguments_invalides(self):
        for nom, arguments in (
            ("inconnu", {}),
            ("statistiques", {}),
            ("statistiques", {"regroupement": "pays"}),
            ("rechercher_produits", {"stock_max": -1}),
            ("rechercher_produits", {"stock_max": True}),
            ("rechercher_produits", {"prix_max": float("nan")}),
            ("rechercher_produits", {"prix_max": None}),
            ("rechercher_fiches", {"sql": "DROP TABLE produits"}),
            ("rechercher_fiches", []),
        ):
            with self.subTest(nom=nom, arguments=arguments):
                with self.assertRaises(ValueError):
                    agent.valider_arguments(nom, arguments)

    def test_croisement_base_et_pdf_et_historique(self):
        self.agent.morceaux = [
            {"document": "NovaTech.pdf", "page": 1, "texte": "NovaTech : livraison 3 jours"}
        ]
        self.client.chat.completions.create.side_effect = [
            reponse_modele(appels=[appel_outil("rechercher_produits", {"stock_max": 0}, "bd")]),
            reponse_modele(appels=[
                appel_outil("rechercher_fiches", {"fournisseur": "NovaTech"}, "pdf")
            ]),
            reponse_modele("Ecran en rupture ; livraison 3 jours [NovaTech.pdf, page 1]."),
        ]
        with patch.object(self.agent, "executer_requete", return_value={
            "source": "Base MySQL : produits",
            "resultats": [{"libelle": "Ecran", "stock": 0, "fournisseur": "NovaTech"}],
        }):
            texte = self.agent.repondre("Ruptures et delais ?")
        self.assertIn("3 jours", texte)
        outils = [m for m in self.agent.messages if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in outils], ["bd", "pdf"])
        self.assertIn("NovaTech.pdf", outils[1]["content"])
        self.assertEqual(self.agent.messages[-1]["content"], texte)

    def test_erreur_mysql_explicite_sans_identifiants(self):
        self.client.chat.completions.create.side_effect = [
            reponse_modele(appels=[appel_outil("rechercher_produits", {}, "bd")]),
            reponse_modele("La base est indisponible."),
        ]
        with patch.object(
            self.agent, "executer_requete",
            side_effect=mysql.connector.Error("mot-de-passe-secret", errno=1045),
        ), patch("sys.stderr"):
            self.agent.repondre("Produits ?")
        resultat = next(m["content"] for m in self.agent.messages if m["role"] == "tool")
        self.assertIn("erreur", resultat)
        self.assertNotIn("mot-de-passe-secret", resultat)

    def test_limite_etapes_force_la_synthese(self):
        self.client.chat.completions.create.side_effect = [
            *[
                reponse_modele(appels=[appel_outil("rechercher_fiches", {}, str(i))])
                for i in range(agent.MAX_ETAPES)
            ],
            reponse_modele("Synthese."),
        ]
        self.assertEqual(self.agent.repondre("Comparer"), "Synthese.")
        self.assertEqual(self.client.chat.completions.create.call_args.kwargs["tool_choice"], "none")

    def test_reponse_vide_ne_corrompt_pas_historique(self):
        self.client.chat.completions.create.return_value = reponse_modele("")
        with self.assertRaises(ValueError):
            self.agent.repondre("Question")
        self.assertEqual(len(self.agent.messages), 1)


if __name__ == "__main__":
    unittest.main()
