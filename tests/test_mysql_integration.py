"""Vérifications MySQL exécutées dans le pipeline sur la base de test."""

import os

import mysql.connector
import pytest

from agent import CatalogueMySQL


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Les tests MySQL d'intégration ne sont activés que dans le pipeline.",
)


def config_mysql():
    return {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.environ["MYSQL_PORT"]),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
    }


def test_outil_recherche_dans_les_donnees_sql_chargees():
    catalogue = CatalogueMySQL(config_mysql())

    resultat = catalogue.rechercher_produits(mot_cle="Écran")

    assert resultat["source"] == "Base MySQL : produits"
    assert {ligne["libelle"] for ligne in resultat["resultats"]} == {
        "Écran 24 pouces Full HD",
        "Écran 27 pouces 4K",
    }


def test_compte_agent_refuse_les_ecritures():
    connexion = mysql.connector.connect(**config_mysql())
    curseur = connexion.cursor()
    try:
        with pytest.raises(mysql.connector.Error) as erreur:
            curseur.execute(
                "INSERT INTO produits "
                "(id, libelle, categorie, prix, stock, fournisseur) "
                "VALUES (9999, 'Test interdit', 'Test', 1.00, 1, 'Test')"
            )
        assert erreur.value.errno == 1142
    finally:
        curseur.close()
        connexion.close()
