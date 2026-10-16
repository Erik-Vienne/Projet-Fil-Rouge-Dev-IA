# Commandes à exécuter (dans l'ordre)

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
