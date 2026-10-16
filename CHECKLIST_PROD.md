# Checklist de préparation à la mise en production

Cette checklist décrit l'état constaté dans le dépôt et les actions à terminer
avant un déploiement réel. « En place » signifie qu'une preuve existe dans le
code ou le pipeline ; « Partiel » signale une protection incomplète ; « À faire »
et « Hébergement » sont des points de préparation, pas des contrôles déjà actifs.
Les identifiants MySQL présents dans les scripts et pipelines actuels sont des
valeurs de démonstration/CI : ne pas les réutiliser en production.

## Sécurité 🔒

| Critère | État | Preuve actuelle et action de mise en production |
|---|---|---|
| Secrets hors du code : `.env` ignoré par Git, secrets GitHub pour le pipeline | Partiel | `.gitignore` ignore `.env` et `.env.*`, avec exception pour `.env.example`. `.env.example` ne contient que des valeurs à remplacer. En revanche, les variables MySQL des pipelines sont actuellement déclarées en clair dans `.github/workflows/tests.yml` et `azure-pipelines.yml`. Remplacer ces valeurs de CI par des secrets GitHub / variables secrètes Azure DevOps et fournir les secrets de production par le gestionnaire de secrets de l'hébergement. Ne jamais mettre une clé réelle dans `.env.example`. |
| Utilisateur MySQL dédié avec le seul droit `SELECT` | Partiel | `sql/00_mysql_base_et_utilisateur.sql` crée `agent_ia` et accorde `GRANT SELECT ON catalogue.*`. Le compte et son mot de passe d'exemple sont codés dans le script. Créer un compte distinct par environnement, définir son secret hors du dépôt et limiter l'accès réseau MySQL aux hôtes applicatifs autorisés. |
| Requêtes paramétrées, pas de SQL libre généré par le LLM | En place | Dans `agent.py`, `executer_requete` appelle `curseur.execute(sql, parametres)` ; les filtres sont construits avec des paramètres `%s`. Les colonnes de regroupement sont autorisées par liste blanche (`categorie`, `fournisseur`). `tests/test_agent.py::test_sql_parametre_et_filtres_zero` vérifie qu'une entrée SQL injectée reste une valeur, pas du SQL. |
| Protection contre l'injection de prompt : instructions, limites | Partiel | `agent.py::SYSTEM_PROMPT` précise que les PDF et résultats SQL sont des données, pas des instructions, et interdit la modification des données. `valider_arguments` contrôle schéma, type et valeurs ; `MAX_ETAPES` borne les appels d'outils. Ces consignes ne constituent pas une garantie contre l'injection de prompt : conserver les outils en lecture seule, ne jamais exécuter d'instruction extraite des documents et ajouter des tests adversariaux avant exposition publique. |
| Dépendances auditées dans le pipeline (`pip-audit`, Dependabot) | À faire | Les pipelines installent `requirements.txt`, mais aucun audit de vulnérabilités ni configuration Dependabot n'est présent. Ajouter `pip-audit` au pipeline (échec sur vulnérabilités selon une politique définie) et activer les mises à jour Dependabot pour `pip` et GitHub Actions. |
| Erreurs techniques non affichées à l'utilisateur | Partiel | Les erreurs MySQL renvoyées à l'agent sont génériques (`agent.py` et `agent_sk.py`), mais `app.py` transmet `str(erreur)` à `st.error` au démarrage et lors d'une réponse. Présenter un message générique à l'utilisateur et conserver uniquement un détail expurgé côté serveur. |

## Optimisation et performance ⚡

| Critère | État | Preuve actuelle et action de mise en production |
|---|---|---|
| Index RAG calculé une seule fois (cache, pas à chaque requête) | En place pour une session | `app.py::initialiser_agent` conserve l'agent dans `st.session_state`; `agent_sk.py::creer_agent` construit `IndexLocal` au démarrage, qui calcule les vecteurs dans son constructeur. Les requêtes réutilisent cet index en mémoire. Un redémarrage ou une nouvelle session le reconstruit : prévoir un cache/persistance partagé si le déploiement a plusieurs workers ou si le coût de démarrage devient important. |
| Résultats SQL limités (`LIMIT`), historique de conversation tronqué | Partiel | `agent.py` définit `MAX_LIGNES = 200`, ajoute `LIMIT MAX_LIGNES + 1` et `fetchmany(MAX_LIGNES + 1)` ; `tests/test_agent.py::test_fermeture_connexion_et_troncature` vérifie la limite. En revanche, `Agent.messages` et l'historique Semantic Kernel s'allongent jusqu'à la réinitialisation de conversation. Borner l'historique (en conservant le message système et les tours complets) et définir une politique de purge. |
| Modèle adapté (ex. mini), `max_tokens` et température maîtrisés | Partiel | `.env.example` propose un déploiement `gpt-5.4-mini-2`, mais l'appel de `agent.py::Agent.repondre` ne fixe ni limite de tokens de sortie ni température ; le choix réel dépend de la configuration Azure. Valider un déploiement adapté au besoin, fixer une borne de sortie compatible avec ce déploiement et mesurer qualité, latence et coût avant mise en service. |
| Ressources partagées (Kernel, pool de connexions MySQL) | Partiel | `AgentSemanticKernel` garde un `Kernel`, un service et les plugins dans une même instance réutilisée par l'application. `CatalogueMySQL.executer_requete` ouvre puis ferme une connexion pour chaque requête (`mysql.connector.connect`). Configurer et dimensionner un pool de connexions pour l'hébergement, puis partager les ressources selon le cycle de vie des sessions/workers. |
| Index MySQL sur les colonnes filtrées, pipeline avec cache pip | Partiel | `sql/01_schema.sql` indexe `fournisseur` et `categorie`. Les filtres SQL portent aussi sur `libelle`, `prix` et `stock` ; examiner `EXPLAIN` et la charge réelle avant d'ajouter des index, notamment pour les recherches `LIKE '%…%'` qui ne bénéficient généralement pas d'un index B-tree classique. `.github/workflows/tests.yml` active `cache: pip` dans `setup-python`; `azure-pipelines.yml` n'a pas de cache pip. Ajouter le cache au pipeline Azure DevOps si celui-ci est conservé. |

## Logs et observabilité 📈

| Critère | État | Preuve actuelle et action de mise en production |
|---|---|---|
| Logs structurés : question, outils appelés, durée, erreurs | À faire | Le code ne met pas en place de journal structuré ni de mesure de durée. L'interface affiche les outils appelés, mais ce n'est pas un journal opérationnel. Ajouter des événements structurés avec identifiant de requête, outils, durée et type d'erreur ; ne pas journaliser le texte brut des questions par défaut. |
| Niveau de log et fichier configurables, avec rotation | À faire | Aucun logger applicatif, niveau configurable ou gestionnaire de rotation n'est configuré. Utiliser les sorties standard et le service de logs de l'hébergement ; rendre le niveau configurable et définir rétention/rotation conformément à la politique de conservation. |
| Suivi des tokens consommés par requête | À faire | Aucune lecture ni journalisation des compteurs d'usage de la réponse du modèle n'est implémentée. Collecter les compteurs de tokens d'entrée/sortie renvoyés par le service, associés à un identifiant de requête et au déploiement, sans enregistrer les prompts. |
| Aucune donnée sensible ni clé dans les logs | Partiel | Aucun journal applicatif des questions ou des clés n'est actuellement configuré. Les erreurs MySQL sont réduites à leur code dans `agent.py` et `agent_sk.py`, et `tests/test_agent.py::test_erreur_mysql_explicite_sans_identifiants` vérifie qu'un secret ne fuit pas dans le résultat d'outil. À la mise en place des logs, expurger secrets, arguments d'outils et données personnelles ; vérifier aussi les sorties d'erreur et la télémétrie de l'hébergeur. |
| Rapport de tests et couverture de code publiés par le pipeline | Partiel | `.github/workflows/tests.yml` publie `test-results.xml` comme artefact ; `azure-pipelines.yml` publie le résultat JUnit. Aucun des deux ne calcule ni ne publie la couverture. Ajouter une mesure (par exemple `pytest-cov`), définir le seuil attendu et publier le rapport de couverture comme artefact. |

## Facturation et coûts 💶

| Critère | État | Preuve actuelle et action de mise en production |
|---|---|---|
| Aucun appel payant dans le pipeline (tests sans Azure OpenAI) | En place dans les tests actuels | `tests/test_agent.py` utilise des clients `MagicMock`; `tests/test_agent_sk.py` remplace les appels chat/embeddings par des `AsyncMock` et teste la création sans appel réseau. Les pipelines ne configurent pas de secrets Azure OpenAI. Garder cette séparation et exécuter tout test d'intégration Azure dans un workflow distinct, explicitement déclenché et plafonné. |
| Coût estimé à partir des tokens journalisés | À faire | Les tokens ne sont pas collectés ou journalisés actuellement. Après mise en place du suivi d'usage, rapprocher les tokens par déploiement des tarifs Azure applicables et publier une estimation périodique ; ne pas assimiler cette estimation à la facture réelle. |
| Quota de tokens par minute sur les déploiements Azure OpenAI | Hébergement | À configurer dans Azure AI Foundry / Azure OpenAI pour chaque déploiement, en cohérence avec le débit maximal attendu et les limites de l'application. Surveiller les réponses de limitation et prévoir une reprise avec temporisation bornée. |
| Budget et alertes de dépense, tags sur la ressource | Hébergement | Créer un budget Azure avec seuils d'alerte et destinataires responsables ; ajouter des tags de propriétaire, projet, environnement et centre de coût aux ressources. Vérifier que les alertes sont effectivement distribuées. |
| Suppression des ressources Azure en fin de formation | Hébergement | Ajouter à la clôture de formation une vérification de l'inventaire Azure (déploiements, ressources IA, groupes de ressources, stockage et ressources associées) puis supprimer celles qui ne sont plus nécessaires. Vérifier la suppression et les coûts résiduels dans Cost Management. |

## Vérifications avant mise en service

- [ ] Remplacer les identifiants de démonstration/CI et vérifier l'historique Git avant tout déploiement.
- [ ] Exécuter les tests et audits de dépendances ; conserver les rapports de tests et de couverture.
- [ ] Vérifier les permissions MySQL, les limites de débit/tokens et les messages d'erreur visibles.
- [ ] Configurer les alertes, la rétention des logs et le budget dans l'environnement cible.
