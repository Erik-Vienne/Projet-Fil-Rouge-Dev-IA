# rag_simple.py
# Le RAG le plus simple possible : les "documents" sont une liste de phrases en mémoire.
# On pose la même question deux fois : SANS le RAG, puis AVEC le RAG.
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
deployment = os.environ["CHAT_DEPLOYMENT"]

# ---------- Nos "documents" : des informations que le LLM ne peut pas connaître ----------
DOCUMENTS = [
    "La formation IA a lieu dans la salle Turing, au 3e étage.",
    "Le code Wi-Fi de la salle de formation est ATOS-2026-IA.",
    "Le formateur de la formation IA s'appelle Sophie Durand.",
    "La pause déjeuner est de 12h30 à 13h30, à la cafétéria du rez-de-chaussée.",
    "La soutenance du projet fil rouge a lieu le jour 10 devant un jury.",
]


# ---------- La recherche : garder les phrases qui partagent des mots avec la question ----------
def chercher(question):
    mots = [mot for mot in question.lower().split() if len(mot) > 3]
    return [doc for doc in DOCUMENTS if any(mot in doc.lower() for mot in mots)]


# ---------- Appel au LLM ----------
def demander(message):
    reponse = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": message}],
    )
    return reponse.choices[0].message.content


question = "Quel est le code Wi-Fi de la salle de formation ?"
print("QUESTION :", question)

# ---------- Simulation 1 : SANS RAG ----------
print("\n========== 1. SANS RAG ==========")
print("On envoie seulement la question.")
print("\nRéponse :", demander(question))

# ---------- Simulation 2 : AVEC RAG ----------
print("\n========== 2. AVEC RAG ==========")
trouves = chercher(question)
print("Documents trouvés :")
for doc in trouves:
    print("   -", doc)

message = (
        "Réponds avec seulement le code :\n"
        + "\n".join(trouves)
        + "\n\nQuestion : " + question
)
print("\nRéponse :", demander(message))