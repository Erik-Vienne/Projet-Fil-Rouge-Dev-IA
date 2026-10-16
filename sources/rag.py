# rag.py
# RAG (Retrieval-Augmented Generation) très simple :
#   1. on lit les PDF du dossier documents/ et on les découpe en morceaux (une page = un morceau)
#   2. pour chaque question, on cherche les morceaux qui contiennent les mêmes mots
#   3. on donne ces morceaux au LLM pour qu'il réponde à partir des documents
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

# ---------- Connexion à Azure OpenAI ----------
load_dotenv()
client = OpenAI(
    base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
deployment = os.environ["CHAT_DEPLOYMENT"]


# ---------- Étape 1 : lire les PDF et les découper en morceaux ----------
def charger_documents(dossier):
    morceaux = []
    for fichier in Path(dossier).glob("*.pdf"):
        lecteur = PdfReader(fichier)
        for numero, page in enumerate(lecteur.pages, start=1):
            morceaux.append({
                "document": fichier.name,
                "source": f"{fichier.name} (page {numero})",
                "texte": page.extract_text() or "",
            })
    return morceaux


# ---------- Étape 2 : trouver les morceaux les plus utiles ----------
def chercher(question, morceaux, nombre=3):
    # On garde les mots de plus de 3 lettres ("le", "de", "est" ne servent à rien)
    mots = [mot for mot in question.lower().split() if len(mot) > 3]

    # Score d'un morceau = nombre de mots de la question qu'il contient
    def score(morceau):
        texte = morceau["texte"].lower()
        return sum(1 for mot in mots if mot in texte)

    morceaux_tries = sorted(
        ((score(morceau), morceau) for morceau in morceaux),
        key=lambda element: element[0],
        reverse=True,
    )
    morceaux_tries = [(note, morceau) for note, morceau in morceaux_tries if note > 0]

    trouves = []
    documents_vus = set()
    for _, morceau in morceaux_tries:
        if morceau["document"] not in documents_vus:
            trouves.append(morceau)
            documents_vus.add(morceau["document"])
            if len(trouves) == nombre:
                return trouves

    for _, morceau in morceaux_tries:
        if morceau not in trouves:
            trouves.append(morceau)
            if len(trouves) == nombre:
                break
    return trouves


# ---------- Étape 3 : demander au LLM de répondre avec ces morceaux ----------
def repondre(question, morceaux_trouves, historique):
    contexte = ""
    for morceau in morceaux_trouves:
        contexte += f"[Source : {morceau['source']}]\n{morceau['texte']}\n\n"

    message_utilisateur = {
        "role": "user",
        "content": f"Documents :\n{contexte}\nQuestion : {question}",
    }
    messages = [
        {
            "role": "system",
            "content":
                "Tu es un assistant qui répond aux questions sur les clients d'Atos. "
                "Réponds UNIQUEMENT à partir des documents fournis. "
                "Si la réponse n'est pas dans les documents, dis : « Je ne trouve pas cette information. » "
                "Indique la source à la fin de ta réponse.",
        },
        *historique,
        message_utilisateur,
    ]
    reponse = client.chat.completions.create(model=deployment, messages=messages)
    texte_reponse = reponse.choices[0].message.content
    historique.extend([message_utilisateur, {"role": "assistant", "content": texte_reponse}])
    return texte_reponse


# ---------- Programme principal ----------
morceaux = charger_documents("documents")
print(f"{len(morceaux)} morceaux chargés depuis le dossier documents/.")
print("Pose une question sur les clients d'Atos (tape quit pour quitter).\n")
historique = []

while True:
    question = input("Vous > ").strip()
    if question.lower() == "quit":
        break
    if not question:
        continue

    trouves = chercher(question, morceaux)
    print("   Morceaux utilisés :", ", ".join(m["source"] for m in trouves))

    print("\nAssistant >", repondre(question, trouves, historique), "\n")