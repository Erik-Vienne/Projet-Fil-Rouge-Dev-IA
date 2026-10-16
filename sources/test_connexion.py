# test_connexion.py : vérifie que Python arrive à lire la base MySQL (sans IA).
import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()
connexion = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
    database=os.getenv("MYSQL_DATABASE", "boutique"),
)
curseur = connexion.cursor()
curseur.execute("SELECT COUNT(*) FROM produits")
print("Connexion réussie ! Nombre de produits :", curseur.fetchone()[0])
connexion.close()
