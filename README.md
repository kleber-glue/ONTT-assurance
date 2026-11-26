# Fassurance - Générateur Oracle pour bordereaux

Application Flask permettant d'importer un fichier Excel, de valider les anomalies,
de configurer les règles métier Oracle et de produire un script SQL téléchargeable.

## Fonctionnalités

- Import XLSX avec OpenPyXL
- Validation des colonnes obligatoires
- Préservation des zéros initiaux
- Aperçu des données
- Correspondances Oracle par code erreur, avec une ou plusieurs tables configurées
  par correspondance et un `UPDATE` généré pour chaque table
- Validation métier avant génération
- Génération Oracle sans connexion ni exécution automatique
- Transaction assistée par contrôles et `ROLLBACK`
- Historique SQLite
- Déploiement Docker Compose

## Installation locale

```powershell
python -m pip install -r requirements.txt
python run.py
```

Le port est lu depuis `.env` (`PORT`, par défaut `50100`). L'application est disponible
sur `http://localhost:50100`.

## Configuration

1. Importer le fichier XLSX.
2. Renseigner le numéro de bordereau et l'année.
3. Ouvrir Configuration métier.
4. Ajouter une correspondance Oracle par code erreur, puis ajouter une ou plusieurs
   tables dans cette correspondance. Renseigner les noms réels des tables et colonnes
   validés par l'équipe technique (identifiants commençant par une lettre). Les tables
   d'une correspondance génèrent des `UPDATE` uniquement pour les lignes de son code
   erreur JSON. Pour la colonne du bordereau, saisir le nom de la colonne, pas le numéro.
5. Valider les données.
6. Générer puis télécharger le fichier SQL.

## Docker

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Docker publie le port défini par `PORT` sur l'hôte et conserve le port interne `5000`.

Les volumes Docker persistent SQLite, les imports et les scripts générés.

## Tests

```powershell
python -m pytest -q
```

## Sécurité SQL

- Aucun UPDATE n'est généré sans clause `WHERE`.
- Les noms de table et de colonne sont validés.
- Les apostrophes sont échappées.
- Les valeurs Oracle sont typées.
- Les lignes invalides ou sans règle active sont exclues.
- Le script ne contient aucun `COMMIT` automatique.
