# TFE Hub Live

Plateforme professionnelle de partage de projets TFE.

## Fonctionnalités

- Comptes utilisateurs (inscription / connexion)
- Base de données SQLite (users, projects, comments, messages)
- Recherche et filtres par domaine
- Likes sur les projets
- Page détail + commentaires
- Chat en temps réel (SocketIO)
- Interface sobre et professionnelle

## Lancement

```bash
pip install -r requirements.txt
python app.py
```

## Déploiement Render

Start Command :
```
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --bind 0.0.0.0:$PORT app:app
```
