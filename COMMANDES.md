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
Un plugin `fiches` expose la recherche sémantique PDF avec embeddings locaux.

Les variables `.env` sont les mêmes que pour `agent.py`.
Aucun déploiement d'embeddings n'est nécessaire ; `EMBEDDING_DEPLOYMENT`, si encore
présente dans un ancien `.env`, est ignorée.
`AZURE_OPENAI_API_VERSION` est optionnelle (par défaut `2024-10-21`).
Configurer `MYSQL_USER=agent_ia`, avec le mot de passe correspondant au compte
limité à `SELECT` créé par `sql\00_mysql_base_et_utilisateur.sql` ; ne pas utiliser
le compte administrateur. Chaque requête s'exécute également dans une transaction
en lecture seule. Aucun outil ne permet d'envoyer du SQL libre.
Les prix et valeurs de stock sont exprimés en euros HT.

## Lot 3 : interface de chat web

Après l'installation des dépendances et la configuration du fichier `.env`,
lancer l'interface depuis la racine du projet :

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\app.py
```

Le fil conserve le contexte pendant la session, les réponses sont rendues en
Markdown et la barre latérale permet de démarrer une nouvelle conversation.
Les appels d'outils effectués pour chaque réponse peuvent être consultés sous
celle-ci. Le nombre de tokens d'entrée et de sortie, cumulé sur les appels de
modèle nécessaires à la réponse, est également affiché. Une question déjà posée
dans la conversation réutilise sa réponse après normalisation des accents, de la
casse et de la ponctuation, sans appeler le modèle ni les outils. Pour obtenir
des données actualisées, démarrez une nouvelle conversation, ce qui efface aussi
ce cache.
Les événements opérationnels sont écrits en JSON sur `stderr` (collectable par
l'hébergement) ; configurez leur niveau avec `LOG_LEVEL` dans `.env`. Le texte
des questions et les arguments d'outils ne sont pas journalisés.

Exemples de conversation :
« Quels produits sont en rupture ? », puis « Quels sont les délais de leurs fournisseurs ? ».
Autres exemples : « Quels produits coûtent entre 50 et 200 euros HT ? »,
« Liste les produits du fournisseur ErgoMobil ».
Les limites documentaires et SQL décrites ci-dessous s'appliquent aux deux agents,
sauf la recherche lexicale, propre à `agent.py`.

## Recherche PDF avec embeddings locaux

Au démarrage, `agent_sk.py` découpe les pages selon la limite de tokens du modèle,
avec chevauchement, puis calcule les embeddings sur CPU avec Sentence Transformers.
Le modèle multilingue par défaut est
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
Le premier lancement nécessite Internet pour télécharger ses fichiers depuis
Hugging Face ; les suivants utilisent le cache local. Aucun texte PDF ni question
n'est envoyé à Hugging Face pour la vectorisation. Le chargement et les calculs
peuvent prendre du temps. Aucun compte Azure supplémentaire n'est nécessaire.

`LOCAL_EMBEDDING_MODEL` peut désigner un autre modèle Sentence Transformers ou un
dossier local contenant un modèle déjà téléchargé. Pour interdire toute connexion
au Hub après téléchargement, définir `HF_HUB_OFFLINE=1`.
L'index des PDF reste en mémoire et est reconstruit à chaque lancement.
Une erreur de chargement ou d'indexation est signalée, sans repli lexical silencieux.

L'outil `fiches-rechercher_fiches` classe les extraits par similarité cosinus,
renvoie les cinq meilleurs par défaut (`nombre` de 1 à 20) et signale la troncature.
Il conserve fichier, page et numéro d'extrait. Le filtre optionnel par fournisseur
sélectionne toutes les pages de ses documents ; une recherche vide les consulte
toutes. Un score ne garantit pas la présence de la réponse dans un extrait.
Cette solution fournit un RAG sémantique, mais déroge à l'exigence du lot 2 de
calculer les embeddings avec un service Azure OpenAI via Semantic Kernel.

```powershell
.\.venv\Scripts\python.exe .\agent_sk.py --question "Quel est le téléphone du fournisseur du switch 24 ports ?"
```

L'agent peut rechercher le produit dans MySQL, récupérer son fournisseur, puis
interroger sa fiche et citer `[nom_du_fichier.pdf, page N]` ainsi que
`[Base MySQL : produits]`. Seul le déploiement de chat Azure OpenAI est utilisé.

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

## Tests unitaires et pipelines CI

Lancer les tests localement, sans appeler Azure OpenAI :

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Les tests couvrent les outils MySQL, le refus des écritures, ainsi que le
découpage et la recherche RAG avec des services simulés. Les vérifications
nécessitant une base MySQL sont ignorées localement ; les pipelines GitHub
Actions (`.github\workflows\tests.yml`) et Azure DevOps (`azure-pipelines.yml`)
démarrent chacun un MySQL isolé, exécutent `sql\00_mysql_base_et_utilisateur.sql`,
`sql\01_schema.sql` et `sql\02_donnees.sql`, puis vérifient l'accès en lecture
seule et les données chargées. Chaque push sur `main` ou `master` déclenche
les tests. GitHub Actions publie le rapport JUnit comme artefact ; Azure DevOps
publie les résultats dans l'onglet **Tests** du pipeline. Tout échec de test
fait échouer le pipeline.

Ne pas committer `.env` ni de vraies clés ou mots de passe. `.env` est ignoré
par Git ; utiliser `.env.example` comme modèle et remplacer ses valeurs
indicatives uniquement dans le fichier local `.env`.
