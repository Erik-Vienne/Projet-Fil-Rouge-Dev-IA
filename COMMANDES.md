# Commandes à exécuter (dans l'ordre)

## Lot 1 : agent Semantic Kernel

Installer les dépendances mises à jour, puis lancer le nouvel agent :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\agent_sk.py
.\.venv\Scripts\python.exe .\agent_sk.py --question "Quelle est la valeur du stock par catégorie ?"
```

`agent_sk.py` crée un `Kernel` connecté à `AzureChatCompletion` et enregistre
un plugin `catalogue` avec cinq fonctions `@kernel_function` :
`rechercher_produits`, `produits_fournisseur`, `stock_faible`,
`fourchette_prix` (bornes incluses) et `statistiques` (dont la valeur du stock,
somme des prix unitaires HT multipliés par les quantités).
`FunctionChoiceBehavior.Auto` laisse le modèle choisir et appeler les outils,
avec au maximum huit étapes automatiques avant synthèse.
`ChatHistory` conserve les échanges, appels d'outils et résultats pendant la session.
Un plugin `fiches` conserve la recherche PDF pour les questions mixtes.

Les variables `.env` sont les mêmes que pour `agent.py`.
`AZURE_OPENAI_API_VERSION` est optionnelle (par défaut `2024-10-21`).
Configurer `MYSQL_USER=agent_ia`, avec le mot de passe correspondant au compte
limité à `SELECT` créé par `sql\00_mysql_base_et_utilisateur.sql` ; ne pas utiliser
le compte administrateur. Chaque requête s'exécute également dans une transaction
en lecture seule. Aucun outil ne permet d'envoyer du SQL libre.
Les prix et valeurs de stock sont exprimés en euros HT.

Exemples de conversation :
« Quels produits sont en rupture ? », puis « Quels sont les délais de leurs fournisseurs ? ».
Autres exemples : « Quels produits coûtent entre 50 et 200 euros HT ? »,
« Liste les produits du fournisseur ErgoMobil ».
Les limites documentaires et SQL décrites ci-dessous s'appliquent aux deux agents.

## Agent catalogue et fiches fournisseurs

L'agent `agent.py`, à la racine, combine les exemples de `sources` et utilise
le schéma de `sql\01_schema.sql` : produits, catégories, prix HT, stocks et
fournisseurs. Les requêtes sont prédéfinies, paramétrées et en lecture seule.
Utiliser un compte MySQL limité à `SELECT`, comme celui créé par
`sql\00_mysql_base_et_utilisateur.sql`.

Après installation des dépendances, renseigner dans `.env` :
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `CHAT_DEPLOYMENT`,
`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`.
Cet agent utilise une clé Azure OpenAI, comme les exemples de `sources` ;
l'authentification Entra ID n'est pas implémentée.

```powershell
.\.venv\Scripts\python.exe .\agent.py
.\.venv\Scripts\python.exe .\agent.py --question "Quels produits sont en rupture et quels sont les délais de leurs fournisseurs ?"
```

Tous les PDF de `fiches_fournisseurs` (sous-dossiers inclus) sont chargés
au démarrage, indépendamment du dossier depuis lequel le script est lancé.
Relancer l'agent après ajout ou modification d'une fiche. Les PDF doivent
contenir du texte extractible ; les scans nécessitent un OCR préalable.
La recherche documentaire est lexicale, sans embeddings ni index externe ;
l'agent peut aussi consulter l'ensemble des fiches pour comparer les fournisseurs.
Les réponses doivent citer le fichier et la page, ou la table MySQL.
Les requêtes SQL renvoient au maximum 200 lignes et signalent toute troncature.
Les données sont interrogées à chaque appel d'outil, sans copie locale de la base.
Les extraits et résultats nécessaires à la réponse sont envoyés au déploiement
Azure OpenAI configuré. Les identifiants MySQL ne sont pas inclus dans les outils.
L'historique reste en mémoire pendant la session ; `quit`, `exit` ou `quitter`
termine la conversation.

## Exemples de formation d'origine

Décompresse le zip, ouvre le dossier `etape1-llm` dans VS Code,
puis ouvre le terminal : menu **Terminal → Nouveau terminal**.

## 1. Créer le fichier .env

Windows (PowerShell) :
```powershell
Copy-Item .env.example .env
```
macOS / Linux :
```bash
cp .env.example .env
```
Ouvre `.env` et remplis les 3 valeurs :
- `AZURE_OPENAI_ENDPOINT` : ex. `https://flpdev.openai.azure.com`
- `AZURE_OPENAI_API_KEY` : ta clé (régénérée)
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` : ex. `gpt-5.4-mini-2`

## 2. Créer l'environnement virtuel

```bash
python -m venv .venv
```
(macOS / Linux : `python3` si `python` n'existe pas.)

## 3. Activer l'environnement virtuel

Windows (PowerShell) :
```powershell
.venv\Scripts\Activate.ps1
```
Si PowerShell refuse :
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Windows (cmd) :
```cmd
.venv\Scripts\activate.bat
```
macOS / Linux :
```bash
source .venv/bin/activate
```
Tu dois voir `(.venv)` au début de la ligne.

## 4. Installer les dépendances

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Choisir l'interpréteur dans VS Code

`Ctrl+Shift+P` → **Python: Select Interpreter** → celui du dossier `.venv`.

## 6. Exécuter

```bash
python etape1_llm.py
```

Résultat attendu (le texte varie) :
```
Un LLM est un modèle d'IA entraîné sur d'immenses quantités de texte...
Tokens utilisés : 87
```

## Conversation interactive dans le terminal

Avec le même fichier `.env` et l'environnement virtuel activé :

```powershell
python etape2_terminal.py
```

Saisis une question après `Vous :`, puis appuie sur Entrée. Le LLM répond
en français et conserve le contexte pendant cette session en recevant tout
l'historique à chaque appel. Le nombre de tokens affiché inclut cet historique.
Tape `quitter`, `exit` ou `quit`, ou utilise `Ctrl+C`, pour terminer.
L'historique n'est pas sauvegardé après la fermeture du programme.

## Erreurs fréquentes

| Message | Cause |
|---|---|
| `KeyError: 'AZURE_OPENAI_ENDPOINT'` | `.env` absent ou variable non remplie |
| `401 Unauthorized` | Clé API incorrecte |
| `404 DeploymentNotFound` | Nom de déploiement incorrect |
| `ModuleNotFoundError: dotenv` | `.venv` non activé ou étape 4 oubliée |
