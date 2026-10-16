-- =============================================================
-- Projet Agent IA - Schéma de la base "catalogue"
-- MySQL 8 / MariaDB 10.x (XAMPP) - à exécuter dans la base "catalogue"
-- =============================================================
SET NAMES utf8mb4;

DROP TABLE IF EXISTS produits;

CREATE TABLE produits (
    id           INTEGER       NOT NULL PRIMARY KEY,
    libelle      VARCHAR(150)  NOT NULL,
    categorie    VARCHAR(50)   NOT NULL,
    prix         DECIMAL(10,2) NOT NULL CHECK (prix >= 0),   -- prix unitaire en euros HT
    stock        INTEGER       NOT NULL CHECK (stock >= 0),  -- quantité disponible
    fournisseur  VARCHAR(100)  NOT NULL                      -- raison sociale (voir fiches PDF)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_produits_fournisseur ON produits (fournisseur);
CREATE INDEX idx_produits_categorie   ON produits (categorie);
