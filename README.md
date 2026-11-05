# TFE Hub Live

Plateforme de partage de projets TFE **avec base de données** et **chat en temps réel**.

## Fonctionnalités

- **Base de données SQLite** (projets + messages)
- **Chat live** (WebSocket via Flask-SocketIO)
- Dépôt de projets en direct (mise à jour instantanée pour tous)
- Interface moderne (Tailwind)
- Historique des messages persisté

## Lancement local

```bash
cd tfe_hub_live
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Ouvre → http://localhost:5000

## Structure

```
tfe_hub_live/
├── app.py                 # Backend Flask + SocketIO + SQLAlchemy
├── requirements.txt
├── data/                  # Base SQLite (créée auto)
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

## Technologies

| Partie          | Techno                |
|-----------------|-----------------------|
| Backend         | Flask                 |
| Temps réel      | Flask-SocketIO        |
| Base de données | SQLite + SQLAlchemy   |
| Frontend        | HTML + Tailwind + JS  |

## Déploiement

- **Render** / **Railway** / **PythonAnywhere** (recommandé pour le chat live)
- Ou VPS avec `gunicorn --worker-class eventlet -w 1 app:app`

---

TFE Informatique 2025/2026
