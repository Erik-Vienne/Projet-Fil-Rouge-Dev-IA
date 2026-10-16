import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import mysql.connector
from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletion
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import AuthorRole
from semantic_kernel.functions import KernelArguments

from agent import CatalogueMySQL
from agent_sk import AgentSemanticKernel, CataloguePlugin, creer_agent
from rag_local import IndexLocal
from test_rag_local import modele_simule


def completion(contenu=None, fonction=None, arguments=None):
    message = {"role": "assistant", "content": contenu}
    if fonction:
        message["tool_calls"] = [{
            "id": "appel_1",
            "type": "function",
            "function": {"name": fonction, "arguments": json.dumps(arguments or {})},
        }]
    return ChatCompletion(
        id="test", object="chat.completion", created=0, model="test",
        choices=[{
            "index": 0,
            "finish_reason": "tool_calls" if fonction else "stop",
            "message": message,
        }],
    )


class PluginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalogue = MagicMock(spec=CatalogueMySQL)
        self.catalogue.rechercher_produits.return_value = {"resultats": []}
        self.catalogue.statistiques.return_value = {"resultats": []}
        self.plugin = CataloguePlugin(self.catalogue)

    async def test_cinq_outils_deleguent_aux_requetes_parametrees(self):
        await self.plugin.rechercher_produits("ecran", "Informatique")
        self.catalogue.rechercher_produits.assert_called_with(
            mot_cle="ecran", categorie="Informatique"
        )
        await self.plugin.produits_fournisseur("ErgoMobil")
        self.catalogue.rechercher_produits.assert_called_with(fournisseur="ErgoMobil")
        await self.plugin.stock_faible(0)
        self.catalogue.rechercher_produits.assert_called_with(stock_max=0)
        await self.plugin.fourchette_prix(0, 200)
        self.catalogue.rechercher_produits.assert_called_with(prix_min=0, prix_max=200)
        await self.plugin.statistiques("categorie")
        self.catalogue.statistiques.assert_called_with(regroupement="categorie")

    async def test_arguments_invalides_ne_consultent_pas_mysql(self):
        for methode, arguments in (
            (self.plugin.stock_faible, (-1,)),
            (self.plugin.stock_faible, (True,)),
            (self.plugin.stock_faible, (1.5,)),
            (self.plugin.fourchette_prix, (200, 50)),
            (self.plugin.fourchette_prix, (float("inf"), 200)),
            (self.plugin.produits_fournisseur, (" ",)),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    await methode(*arguments)
        self.catalogue.rechercher_produits.assert_not_called()

    async def test_erreur_mysql_signalee_sans_secret(self):
        self.catalogue.rechercher_produits.side_effect = mysql.connector.Error(
            "secret-local", errno=1045
        )
        with patch("sys.stderr"):
            resultat = await self.plugin.stock_faible()
        self.assertIn("erreur", json.loads(resultat))
        self.assertNotIn("secret-local", resultat)


class KernelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncAzureOpenAI(
            api_key="test", azure_endpoint="https://test.openai.azure.com",
            api_version="2024-10-21",
        )
        self.service = AzureChatCompletion(deployment_name="test", async_client=self.client)
        self.catalogue = MagicMock(spec=CatalogueMySQL)
        self.catalogue.rechercher_produits.return_value = {
            "source": "Base MySQL : produits",
            "resultats": [{"libelle": "Ecran", "stock": 0, "fournisseur": "NovaTech"}],
        }
        self.catalogue.statistiques.return_value = {
            "resultats": [{"categorie": "Audio", "valeur_stock": "1200.00"}]
        }
        self.morceaux = [
            {"document": "NovaTech.pdf", "page": 1, "texte": "NovaTech : 3 jours"}
        ]
        self.index = IndexLocal(self.morceaux, modele_simule())
        self.agent = AgentSemanticKernel(self.service, self.catalogue, self.index)

    async def asyncTearDown(self):
        await self.client.close()

    async def test_enregistrement_et_invocation_des_cinq_fonctions(self):
        self.assertEqual(len(self.agent.kernel.plugins["catalogue"].functions), 5)
        metadata = self.agent.kernel.plugins["catalogue"]["statistiques"].metadata
        self.assertEqual(metadata.parameters[0].schema_data["type"], "string")
        self.assertEqual(
            metadata.parameters[0].schema_data["enum"], ["categorie", "fournisseur"]
        )
        for nom, arguments in (
            ("rechercher_produits", {"mot_cle": "Ecran"}),
            ("produits_fournisseur", {"fournisseur": "NovaTech"}),
            ("stock_faible", {"seuil": 0}),
            ("fourchette_prix", {"prix_min": 0, "prix_max": 200}),
            ("statistiques", {"regroupement": "categorie"}),
        ):
            with self.subTest(nom=nom):
                resultat = await self.agent.kernel.invoke(
                    plugin_name="catalogue", function_name=nom,
                    arguments=KernelArguments(**arguments),
                )
                self.assertFalse(resultat.metadata.get("exception"))
                self.assertIn("resultats", json.loads(str(resultat)))

    async def test_auto_invoque_statistiques_avec_enum(self):
        create = AsyncMock(side_effect=[
            completion(fonction="catalogue-statistiques", arguments={"regroupement": "categorie"}),
            completion("Audio : 1200 euros HT."),
        ])
        with patch.object(self.client.chat.completions, "create", create):
            await self.agent.repondre("Valeur du stock par categorie ?")
        self.catalogue.statistiques.assert_called_once_with(regroupement="categorie")

    async def test_auto_invoque_outil_et_conserve_historique_multitours(self):
        create = AsyncMock(side_effect=[
            completion(fonction="catalogue-stock_faible", arguments={"seuil": 0}),
            completion("Ecran en rupture [Base MySQL : produits]."),
            completion(fonction="fiches-rechercher_fiches", arguments={"fournisseur": "NovaTech"}),
            completion("Livraison 3 jours [NovaTech.pdf, page 1]."),
        ])
        with patch.object(self.client.chat.completions, "create", create):
            self.assertIn("rupture", await self.agent.repondre("Quels produits sont en rupture ?"))
            self.assertIn("3 jours", await self.agent.repondre("Et leur delai de livraison ?"))
        self.catalogue.rechercher_produits.assert_called_once_with(stock_max=0)
        roles = [m.role for m in self.agent.historique.messages]
        self.assertEqual(roles.count(AuthorRole.USER), 2)
        self.assertEqual(roles.count(AuthorRole.TOOL), 2)
        self.assertEqual(create.call_args_list[0].kwargs["tool_choice"], "auto")
        derniers_messages = create.call_args.kwargs["messages"]
        self.assertTrue(any("Ecran en rupture" in str(m) for m in derniers_messages))
        self.assertTrue(any("NovaTech.pdf" in str(m) for m in derniers_messages))

    async def test_echec_ne_corrompt_pas_historique(self):
        with patch.object(
            self.client.chat.completions, "create",
            AsyncMock(return_value=completion("")),
        ):
            with self.assertRaises(ValueError):
                await self.agent.repondre("Question")
        self.assertEqual(len(self.agent.historique.messages), 1)

    async def test_question_mixte_telephone_sans_embeddings_azure(self):
        self.catalogue.rechercher_produits.return_value = {
            "source": "Base MySQL : produits",
            "resultats": [{
                "libelle": "Switch 24 ports Gigabit", "fournisseur": "NetLink Systemes",
            }],
        }
        self.index.extraits[:] = [{
            "document": "NetLink.pdf", "page": 2,
            "texte": "NetLink Systemes : telephone 01 23 45 67 89",
        }]
        create = AsyncMock(side_effect=[
            completion(
                fonction="catalogue-rechercher_produits",
                arguments={"mot_cle": "Switch 24 ports"},
            ),
            completion(
                fonction="fiches-rechercher_fiches",
                arguments={"recherche": "telephone",
                           "fournisseur": "NetLink Systemes"},
            ),
            completion(
                "01 23 45 67 89 [NetLink.pdf, page 2] [Base MySQL : produits]."
            ),
        ])
        with (
            patch.object(self.client.chat.completions, "create", create),
            patch.object(self.client.embeddings, "create", AsyncMock()) as generer,
        ):
            texte = await self.agent.repondre(
                "Quel est le telephone du fournisseur du switch 24 ports ?"
            )
        self.catalogue.rechercher_produits.assert_called_once_with(
            mot_cle="Switch 24 ports", categorie=""
        )
        generer.assert_not_awaited()
        outils = [m for m in self.agent.historique.messages if m.role == AuthorRole.TOOL]
        self.assertEqual(len(outils), 2)
        resultat = json.loads(str(outils[-1].items[0]))
        self.assertEqual(resultat["resultats"][0]["document"], "NetLink.pdf")
        self.assertEqual(resultat["recherche"], "semantique locale")
        self.assertAlmostEqual(resultat["resultats"][0]["score"], 1)
        self.assertIn("NetLink.pdf", texte)
        self.assertIn("page 2", texte)

    async def test_creation_sans_deploiement_embeddings_ni_appel_reseau(self):
        with (
            patch("agent_sk.charger_configuration", return_value={}),
            patch.dict("os.environ", {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_OPENAI_API_KEY": "test",
                "CHAT_DEPLOYMENT": "test",
                "EMBEDDING_DEPLOYMENT": "",
            }),
            patch("agent_sk.AsyncAzureOpenAI", return_value=self.client),
            patch("agent_sk.charger_modele", return_value=modele_simule()),
            patch.object(self.client.embeddings, "create", AsyncMock()) as embeddings,
            patch.object(self.client.chat.completions, "create", AsyncMock()) as chat,
        ):
            agent = creer_agent()
        embeddings.assert_not_awaited()
        chat.assert_not_awaited()
        self.assertEqual(len(agent.kernel.services), 1)
        self.assertIn("fiches", agent.kernel.plugins)


class RequetesTests(unittest.TestCase):
    def test_fourchette_inclusive_et_valeur_stock(self):
        catalogue = CatalogueMySQL({})
        with patch.object(catalogue, "executer_requete") as executer:
            catalogue.rechercher_produits(prix_min=50, prix_max=200)
            sql, parametres = executer.call_args.args
            self.assertIn("prix >= %s", sql)
            self.assertIn("prix <= %s", sql)
            self.assertEqual(parametres, [200, 50])
            catalogue.statistiques("categorie")
            self.assertIn("SUM(prix * stock)", executer.call_args.args[0])

    def test_transaction_lecture_seule(self):
        connexion = MagicMock()
        connexion.cursor.return_value.fetchmany.return_value = []
        with patch("agent.mysql.connector.connect", return_value=connexion):
            CatalogueMySQL({}).executer_requete("SELECT id FROM produits")
        self.assertEqual(
            connexion.cursor.return_value.execute.call_args_list[0].args,
            ("START TRANSACTION READ ONLY",),
        )
        connexion.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
