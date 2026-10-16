import unittest

from app import extraire_appels_outils


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


if __name__ == "__main__":
    unittest.main()
