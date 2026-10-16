import unittest
from unittest.mock import patch

from app import (
    afficher_consommation,
    afficher_origine_reponse,
    extraire_appels_outils,
)


class AppTests(unittest.TestCase):
    def test_extrait_les_appels_outils_des_messages_assistant(self):
        messages = [
            {"role": "user", "content": "Stock ?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "catalogue-stock_faible",
                            "arguments": '{"seuil": 0}',
                        }
                    }
                ],
            },
            {"role": "tool", "content": '{"resultats": []}'},
        ]
        self.assertEqual(extraire_appels_outils(messages), [{
            "nom": "catalogue-stock_faible",
            "arguments": {"seuil": 0},
        }])

    def test_conserve_les_arguments_invalides_visibles(self):
        messages = [{
            "role": "assistant",
            "tool_calls": [{
                "function": {
                    "name": "rechercher_fiches",
                    "arguments": "{",
                }
            }],
        }]
        self.assertEqual(extraire_appels_outils(messages), [{
            "nom": "rechercher_fiches",
            "arguments": {"arguments": "{"},
        }])

    def test_affiche_la_consommation_de_tokens_sans_tarif(self):
        with patch("app.st.caption") as caption:
            afficher_consommation({
                "tokens_entree": 1000, "tokens_sortie": 500, "tokens_total": 1500,
            })
        caption.assert_called_once_with(
            "Tokens : 1 500 au total (1 000 en entrée, 500 en sortie)"
        )

    def test_signale_une_consommation_indisponible(self):
        with patch("app.st.caption") as caption:
            afficher_consommation(None)
        caption.assert_called_once_with("Consommation de tokens indisponible.")

    def test_signale_une_reponse_reprise_de_l_historique(self):
        with patch("app.st.caption") as caption:
            afficher_origine_reponse(True)
        caption.assert_called_once_with(
            "Réponse reprise de l’historique, sans nouvel appel au modèle."
        )


if __name__ == "__main__":
    unittest.main()
