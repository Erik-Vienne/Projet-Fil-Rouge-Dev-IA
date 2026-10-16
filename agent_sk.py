"""Agent Semantic Kernel : catalogue MySQL et embeddings locaux sur les fiches PDF."""

import argparse
import asyncio
import json
import math
import os
import sys
from enum import Enum
from typing import Annotated

import mysql.connector
from openai import APIError, AsyncAzureOpenAI
from pypdf.errors import PdfReadError
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.contents import ChatHistory
from semantic_kernel.exceptions import KernelException
from semantic_kernel.functions import kernel_function

from agent import (
    DOSSIER_FICHES,
    MAX_ETAPES,
    SYSTEM_PROMPT,
    CatalogueMySQL,
    charger_configuration,
    charger_documents,
)
from rag_local import IndexLocal, charger_modele


def verifier_nombre(valeur, nom, entier=False):
    if (
        type(valeur) not in (int, float)
        or not math.isfinite(valeur)
        or valeur < 0
        or (entier and type(valeur) is not int)
    ):
        raise ValueError(f"{nom} doit etre un nombre positif ou nul"
                         + (" entier." if entier else "."))


class Regroupement(str, Enum):
    CATEGORIE = "categorie"
    FOURNISSEUR = "fournisseur"


class CataloguePlugin:
    """Expose uniquement des SELECT predetermines ; aucun SQL fourni par le modele."""

    def __init__(self, catalogue: CatalogueMySQL):
        self.catalogue = catalogue

    async def _executer(self, fonction, **arguments) -> str:
        try:
            resultat = await asyncio.to_thread(fonction, **arguments)
        except mysql.connector.Error as erreur:
            print(f"Erreur MySQL (code {erreur.errno}).", file=sys.stderr)
            resultat = {"erreur": "Acces MySQL impossible. Aucune donnee disponible."}
        return json.dumps(resultat, ensure_ascii=False, default=str)

    @kernel_function(description="Recherche les produits MySQL par mot du libelle et categorie.")
    async def rechercher_produits(
        self,
        mot_cle: Annotated[str, "Partie du libelle ; vide pour tous les produits"] = "",
        categorie: Annotated[str, "Partie de la categorie ; vide sans filtre"] = "",
    ) -> str:
        return await self._executer(
            self.catalogue.rechercher_produits, mot_cle=mot_cle, categorie=categorie
        )

    @kernel_function(description="Liste les produits, prix HT et stocks d'un fournisseur.")
    async def produits_fournisseur(
        self, fournisseur: Annotated[str, "Nom ou partie du nom du fournisseur"]
    ) -> str:
        if not fournisseur.strip():
            raise ValueError("Le nom du fournisseur est obligatoire.")
        return await self._executer(
            self.catalogue.rechercher_produits, fournisseur=fournisseur
        )

    @kernel_function(description="Produits dont le stock est au plus le seuil ; 0 = ruptures.")
    async def stock_faible(
        self, seuil: Annotated[int, "Seuil entier positif ou nul ; 0 pour les ruptures"] = 10
    ) -> str:
        verifier_nombre(seuil, "seuil", entier=True)
        return await self._executer(self.catalogue.rechercher_produits, stock_max=seuil)

    @kernel_function(description="Produits dans une fourchette de prix unitaires en euros HT, bornes incluses.")
    async def fourchette_prix(
        self,
        prix_min: Annotated[float, "Prix minimum en euros HT, positif ou nul"],
        prix_max: Annotated[float, "Prix maximum en euros HT, au moins egal au minimum"],
    ) -> str:
        verifier_nombre(prix_min, "prix_min")
        verifier_nombre(prix_max, "prix_max")
        if prix_min > prix_max:
            raise ValueError("prix_min doit etre inferieur ou egal a prix_max.")
        return await self._executer(
            self.catalogue.rechercher_produits, prix_min=prix_min, prix_max=prix_max
        )

    @kernel_function(
        description="Statistiques MySQL par categorie ou fournisseur : nombre de produits, "
        "prix moyen HT, stock total et valeur du stock en euros HT (somme prix * stock)."
    )
    async def statistiques(
        self, regroupement: Annotated[
            Regroupement, "Colonne de regroupement autorisee : categorie ou fournisseur"
        ] = Regroupement.CATEGORIE,
    ) -> str:
        return await self._executer(
            self.catalogue.statistiques, regroupement=Regroupement(regroupement).value
        )


class FichesPlugin:
    def __init__(self, index):
        self.index = index

    @kernel_function(
        description="Recherche semantique locale dans les PDF fournisseurs avec fichier et page. "
        "Sans recherche, lit toutes les fiches ; filtrage optionnel par fournisseur. "
        "Citer le fichier et la page dans la reponse."
    )
    async def rechercher_fiches(
        self,
        recherche: Annotated[str, "Question en langage naturel ; vide pour toutes les pages"] = "",
        fournisseur: Annotated[str, "Nom du fournisseur ou reference FRN"] = "",
        nombre: Annotated[int, "Maximum d'extraits semantiques, de 1 a 20"] = 5,
    ) -> str:
        return json.dumps(
            await asyncio.to_thread(self.index.rechercher, recherche, fournisseur, nombre),
            ensure_ascii=False,
        )


class AgentSemanticKernel:
    def __init__(self, service, catalogue, index):
        self.kernel = Kernel()
        self.service = service
        self.kernel.add_service(service)
        self.kernel.add_plugin(CataloguePlugin(catalogue), plugin_name="catalogue")
        self.kernel.add_plugin(FichesPlugin(index), plugin_name="fiches")
        self.settings = AzureChatPromptExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                maximum_auto_invoke_attempts=MAX_ETAPES,
            ),
        )
        self.historique = ChatHistory(system_message=SYSTEM_PROMPT + """
La recherche des fiches est semantique, avec des embeddings locaux.
Les scores de similarite ne prouvent pas que l'extrait contient la reponse.
Pour un contact lie a un produit, trouve d'abord son fournisseur dans MySQL,
puis interroge les fiches en filtrant sur ce fournisseur.
""")

    async def repondre(self, question: str) -> str:
        if not question.strip():
            raise ValueError("La question ne peut pas etre vide.")
        # SK ajoute les appels et resultats d'outils a cet historique pendant l'invocation.
        historique = self.historique.model_copy(deep=True)
        historique.add_user_message(question)
        reponse = await self.service.get_chat_message_content(
            chat_history=historique, settings=self.settings, kernel=self.kernel,
        )
        if reponse is None or not reponse.content or not reponse.content.strip():
            raise ValueError("Le modele a renvoye une reponse vide.")
        historique.add_message(reponse)
        self.historique = historique
        return reponse.content


def creer_agent():
    config_bd = charger_configuration()
    morceaux = charger_documents(DOSSIER_FICHES)
    index = IndexLocal(morceaux, charger_modele())
    client = AsyncAzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        timeout=60,
        max_retries=1,
    )
    service = AzureChatCompletion(
        deployment_name=os.environ["CHAT_DEPLOYMENT"],
        async_client=client,
    )
    return AgentSemanticKernel(service, CatalogueMySQL(config_bd), index)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", help="Poser une question puis quitter.")
    args = parser.parse_args()
    agent = None
    try:
        agent = creer_agent()
        if args.question:
            print(await agent.repondre(args.question))
            return 0
        print("Agent Semantic Kernel : MySQL + PDF. Tapez quit pour quitter.")
        while True:
            question = input("Vous > ").strip()
            if question.casefold() in ("quit", "exit", "quitter"):
                return 0
            if question:
                print("\nAssistant >", await agent.repondre(question), "\n")
    except (EOFError, KeyboardInterrupt):
        print("\nFin de la conversation.")
        return 0
    except (APIError, KernelException) as erreur:
        print(
            f"Erreur Semantic Kernel / Azure OpenAI ({type(erreur).__name__}). "
            "Verifiez la connexion et la configuration Azure du .env.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, PdfReadError) as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1
    finally:
        if agent is not None:
            await agent.service.client.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nFin de la conversation.")
