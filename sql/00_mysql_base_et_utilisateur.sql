-- =============================================================
-- Création de la base et de l'utilisateur de l'agent, en LECTURE SEULE
-- À exécuter en root sur MySQL / MariaDB (XAMPP), AVANT 01_schema.sql
-- =============================================================
CREATE DATABASE IF NOT EXISTS catalogue CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE catalogue;

CREATE USER IF NOT EXISTS 'agent_ia'@'%' IDENTIFIED BY 'AgentIA_2026!';
CREATE USER IF NOT EXISTS 'agent_ia'@'localhost' IDENTIFIED BY 'AgentIA_2026!';
GRANT SELECT ON catalogue.* TO 'agent_ia'@'%';
GRANT SELECT ON catalogue.* TO 'agent_ia'@'localhost';
FLUSH PRIVILEGES;
