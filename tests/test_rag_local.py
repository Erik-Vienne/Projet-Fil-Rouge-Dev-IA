import unittest
from unittest.mock import MagicMock

import numpy as np

from agent import DOSSIER_FICHES, charger_documents
from rag_local import IndexLocal, verifier_vecteurs


def modele_simule():
    modele = MagicMock()
    modele.max_seq_length = 10
    modele.tokenizer.num_special_tokens_to_add.return_value = 2
    modele.tokenizer.encode.side_effect = lambda texte, **kw: texte.split()
    modele.tokenizer.decode.side_effect = lambda tokens, **kw: " ".join(tokens)
    modele.encode.side_effect = lambda textes, **kw: np.array([[1.0, 0.0] for _ in textes])
    return modele


class IndexLocalTests(unittest.TestCase):
    def setUp(self):
        self.modele = modele_simule()
        self.pages = [
            {"document": "a.pdf", "page": 1, "texte": "NovaTech livraison demain"},
            {"document": "b.pdf", "page": 2, "texte": "NetLink Systemes standard 01 23"},
        ]
        self.modele.encode.return_value = np.array([[10., 0.], [0., 2.]])
        self.modele.encode.side_effect = None
        self.index = IndexLocal(self.pages, self.modele)
        self.modele.encode.return_value = np.array([[0., 5.]])
        self.modele.encode.reset_mock()

    def test_similarite_cosinus_sans_mots_communs_et_sources(self):
        resultat = self.index.rechercher("Comment joindre le support ?", nombre=1)
        extrait = resultat["resultats"][0]
        self.assertEqual(extrait["document"], "b.pdf")
        self.assertEqual(extrait["page"], 2)
        self.assertAlmostEqual(extrait["score"], 1)
        self.assertTrue(resultat["tronque"])
        self.assertEqual(resultat["recherche"], "semantique locale")
        self.modele.encode.assert_called_once()

    def test_filtre_normalise_et_consultation_exhaustive(self):
        resultat = self.index.rechercher(fournisseur="NetLink Systèmes")
        self.assertEqual(len(resultat["resultats"]), 1)
        self.assertEqual(resultat["resultats"][0]["document"], "b.pdf")
        self.assertFalse(resultat["tronque"])
        self.assertEqual(len(self.index.rechercher(nombre=1)["resultats"]), 2)
        self.assertEqual(self.index.rechercher("contact", "inconnu")["resultats"], [])
        self.modele.encode.assert_not_called()

    def test_decoupage_tokens_chevauchement_et_pages_fournisseur(self):
        modele = modele_simule()
        texte = "NetLink Systemes un deux trois quatre cinq six sept huit neuf dix"
        index = IndexLocal([
            {"document": "fiche.pdf", "page": 1, "texte": texte},
            {"document": "fiche.pdf", "page": 2, "texte": "standard 01 23"},
        ], modele)
        self.assertEqual(len(index.extraits), 3)
        self.assertEqual(index.extraits[0]["texte"].split()[-2:],
                         index.extraits[1]["texte"].split()[:2])
        self.assertTrue(all(len(e["texte"].split()) <= 8 for e in index.extraits))
        self.assertEqual(len(index.rechercher(fournisseur="NetLink")["resultats"]), 3)
        self.assertEqual(index.extraits[-1]["page"], 2)

    def test_entrees_et_vecteurs_invalides(self):
        for nombre in (0, 21, True, 1.5):
            with self.assertRaises(ValueError):
                self.index.rechercher("contact", nombre=nombre)
        for vecteurs in ([], [[0, 0]], [[float("nan"), 0]], [[1]], [[float("inf"), 1]]):
            with self.assertRaises(ValueError):
                verifier_vecteurs(vecteurs, 1, 2)
        for pages in ([], [{"document": "a.pdf", "page": 1, "texte": ""}]):
            with self.assertRaises(ValueError):
                IndexLocal(pages, modele_simule())
        self.modele.encode.side_effect = OSError("Modele indisponible")
        with self.assertRaisesRegex(OSError, "Modele indisponible"):
            self.index.rechercher("contact")

    def test_toutes_les_fiches_reelles_indexees(self):
        pages = charger_documents(DOSSIER_FICHES)
        index = IndexLocal(pages, modele_simule())
        self.assertEqual(
            {(e["document"], e["page"]) for e in index.extraits},
            {(p["document"], p["page"]) for p in pages},
        )
        self.assertEqual(len(index.vecteurs), len(index.extraits))


if __name__ == "__main__":
    unittest.main()
