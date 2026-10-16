# agent_bd.py
# Agent IA qui répond aux questions sur les produits d'une base MySQL.
# Le LLM ne voit jamais la base : il choisit un outil, et c'est NOTRE code qui exécute
# des requêtes SQL préparées à l'avance (paramétrées, en lecture seule).
import json
import os

import mysql.connector
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---------- 1. Connexions : Azure OpenAI et MySQL ----------
client = OpenAI(
    base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
deployment = os.environ["CHAT_DEPLOYMENT"]

CONFIG_BD = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.environ["MYSQL_USER"],          # l'utilisateur "agent_ia" : lecture seule
    "password": os.environ["MYSQL_PASSWORD"],
    "database": os.getenv("MYSQL_DATABASE", "boutique"),
}


def executer_requete(sql, parametres=()):
    """Exécute une requête SELECT et renvoie les lignes en texte JSON."""
    connexion = mysql.connector.connect(**CONFIG_BD)
    try:
        curseur = connexion.cursor(dictionary=True)   # chaque ligne = un dictionnaire {colonne: valeur}
        curseur.execute(sql, parametres)               # les %s sont remplacés EN SÉCURITÉ par les paramètres
        lignes = curseur.fetchall()
    finally:
        connexion.close()                              # on ferme toujours la connexion, même en cas d'erreur
    if not lignes:
        return "Aucun résultat."
    # default=float : les prix DECIMAL de MySQL deviennent des nombres lisibles en JSON
    return json.dumps(lignes, ensure_ascii=False, default=float)


# ---------- 2. Les 3 outils : des requêtes SQL préparées ----------
def rechercher_produits(mot_cle=None, pays=None, fournisseur=None, prix_max=None):
    """Outil 1 : recherche des produits avec des filtres optionnels."""
    sql = "SELECT libelle, prix, stock, fournisseur, pays FROM produits WHERE 1=1"
    parametres = []
    if mot_cle:
        sql += " AND libelle LIKE %s"
        parametres.append(f"%{mot_cle}%")
    if pays:
        sql += " AND pays = %s"
        parametres.append(pays)
    if fournisseur:
        sql += " AND fournisseur = %s"
        parametres.append(fournisseur)
    if prix_max is not None:
        sql += " AND prix <= %s"
        parametres.append(prix_max)
    sql += " ORDER BY prix LIMIT 50"
    return executer_requete(sql, parametres)


def produits_stock_faible(seuil=10):
    """Outil 2 : produits dont le stock est inférieur ou égal au seuil (0 = rupture)."""
    sql = ("SELECT libelle, stock, fournisseur FROM produits "
           "WHERE stock <= %s ORDER BY stock")
    return executer_requete(sql, (seuil,))


def statistiques(regroupement):
    """Outil 3 : nombre de produits, prix moyen et stock total, par pays ou par fournisseur."""
    # Un nom de colonne ne peut pas être passé en paramètre %s :
    # on n'accepte donc que des valeurs d'une liste autorisée.
    if regroupement not in ("pays", "fournisseur"):
        return "Regroupement impossible. Valeurs possibles : pays, fournisseur."
    sql = (f"SELECT {regroupement}, COUNT(*) AS nb_produits, "
           f"ROUND(AVG(prix), 2) AS prix_moyen, CAST(SUM(stock) AS SIGNED) AS stock_total "
           f"FROM produits GROUP BY {regroupement} ORDER BY nb_produits DESC")
    return executer_requete(sql)


OUTILS = {
    "rechercher_produits": rechercher_produits,
    "produits_stock_faible": produits_stock_faible,
    "statistiques": statistiques,
}


# ---------- 3. La description des outils, envoyée au LLM ----------
DESCRIPTIONS = [
    {"type": "function", "function": {
        "name": "rechercher_produits",
        "description": "Recherche des produits du magasin (libellé, prix en euros, stock, fournisseur, pays). "
                       "Tous les filtres sont optionnels ; sans filtre, renvoie tous les produits.",
        "parameters": {
            "type": "object",
            "properties": {
                "mot_cle": {"type": "string", "description": "Mot contenu dans le libellé, ex : écran"},
                "pays": {"type": "string", "description": "Pays du fournisseur, ex : France"},
                "fournisseur": {"type": "string", "description": "Nom exact du fournisseur, ex : TechNord"},
                "prix_max": {"type": "number", "description": "Prix maximum en euros"},
            },
            "required": [],
        },
    }},
    {"type": "function", "function": {
        "name": "produits_stock_faible",
        "description": "Liste les produits dont le stock est inférieur ou égal à un seuil. "
                       "Un stock de 0 signifie une rupture.",
        "parameters": {
            "type": "object",
            "properties": {"seuil": {"type": "integer", "description": "Seuil de stock, ex : 10 (0 pour les ruptures)"}},
            "required": ["seuil"],
        },
    }},
    {"type": "function", "function": {
        "name": "statistiques",
        "description": "Statistiques regroupées : nombre de produits, prix moyen et stock total, par pays ou par fournisseur.",
        "parameters": {
            "type": "object",
            "properties": {"regroupement": {"type": "string", "enum": ["pays", "fournisseur"]}},
            "required": ["regroupement"],
        },
    }},
]


# ---------- 4. La boucle de l'agent ----------
SYSTEM_PROMPT = ("Tu es l'assistant du magasin informatique. Tu réponds aux questions sur les produits "
                 "en utilisant UNIQUEMENT les outils : n'invente jamais un produit, un prix ou un stock. "
                 "Les prix sont en euros. Réponds en français, de façon claire et concise.")


def executer_agent(messages):
    """Fait travailler l'agent sur la conversation et renvoie (réponse, outils utilisés)."""
    outils_utilises = []

    for etape in range(5):  # garde-fou : 5 étapes maximum
        reponse = client.chat.completions.create(
            model=deployment, messages=messages, tools=DESCRIPTIONS)
        message = reponse.choices[0].message

        # Cas 1 : pas d'outil demandé -> réponse finale
        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content})
            return message.content, outils_utilises

        # Cas 2 : le LLM demande des outils -> on les exécute
        messages.append(message)
        for appel in message.tool_calls:
            nom_outil = appel.function.name
            arguments = json.loads(appel.function.arguments)
            print(f"   [outil] {nom_outil}({arguments})")
            try:
                resultat = OUTILS[nom_outil](**arguments)
            except Exception as erreur:              # base arrêtée, mauvais mot de passe...
                resultat = f"Erreur lors de l'accès à la base : {erreur}"
            print(f"   [résultat] {resultat[:200]}")
            outils_utilises.append({"outil": nom_outil, "arguments": arguments, "resultat": resultat})
            messages.append({"role": "tool", "tool_call_id": appel.id, "content": resultat})

    return "Désolé, je n'ai pas pu terminer : trop d'étapes.", outils_utilises


# ---------- 5. Le programme dans le terminal ----------
if __name__ == "__main__":
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("Posez une question sur les produits (quit pour quitter).")
    print("Exemple : Quels produits viennent de France et coûtent moins de 500 euros ?\n")

    while True:
        question = input("Vous > ").strip()
        if question.lower() == "quit":
            break
        if not question:
            continue
        messages.append({"role": "user", "content": question})
        reponse, outils = executer_agent(messages)
        print("\nAssistant >", reponse, "\n")
