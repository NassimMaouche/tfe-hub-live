"""
TFE Hub Live
============
Plateforme de partage de projets TFE + chat en temps réel.
Base de données SQLite + Flask-SocketIO.
"""

from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "tfe_hub.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "tfe-hub-secret-change-me-in-prod"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(255), nullable=False)
    auteur = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    domaine = db.Column(db.String(50), nullable=False, default="autre")
    annee = db.Column(db.String(20))
    description = db.Column(db.Text, nullable=False)
    lien = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "titre": self.titre,
            "auteur": self.auteur,
            "domaine": self.domaine,
            "annee": self.annee or "",
            "description": self.description,
            "lien": self.lien or "",
            "created_at": self.created_at.strftime("%d/%m/%Y %H:%M"),
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    room = db.Column(db.String(50), default="general")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "content": self.content,
            "room": self.room,
            "created_at": self.created_at.strftime("%H:%M"),
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template("index.html", projects=projects)


@app.route("/api/projects", methods=["GET"])
def api_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects])


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json() or request.form

    titre = (data.get("titre") or "").strip()
    auteur = (data.get("auteur") or "").strip()
    description = (data.get("description") or "").strip()
    domaine = (data.get("domaine") or "autre").strip()

    if not titre or not auteur or not description:
        return jsonify({"error": "Champs obligatoires manquants"}), 400

    project = Project(
        titre=titre,
        auteur=auteur,
        email=(data.get("email") or "").strip(),
        domaine=domaine,
        annee=(data.get("annee") or "").strip(),
        description=description,
        lien=(data.get("lien") or "").strip(),
    )
    db.session.add(project)
    db.session.commit()

    socketio.emit("new_project", project.to_dict())

    return jsonify(project.to_dict()), 201


@app.route("/api/messages")
def api_messages():
    room = request.args.get("room", "general")
    messages = (
        Message.query.filter_by(room=room)
        .order_by(Message.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([m.to_dict() for m in reversed(messages)])


# ---------------------------------------------------------------------------
# SocketIO – Chat live
# ---------------------------------------------------------------------------
@socketio.on("connect")
def on_connect():
    emit("status", {"msg": "Connecté au chat TFE Hub"})


@socketio.on("join")
def on_join(data):
    username = data.get("username", "Anonyme")
    room = data.get("room", "general")
    join_room(room)
    emit(
        "chat_message",
        {
            "username": "Système",
            "content": f"{username} a rejoint le chat",
            "created_at": datetime.utcnow().strftime("%H:%M"),
            "system": True,
        },
        room=room,
    )


@socketio.on("leave")
def on_leave(data):
    username = data.get("username", "Anonyme")
    room = data.get("room", "general")
    leave_room(room)
    emit(
        "chat_message",
        {
            "username": "Système",
            "content": f"{username} a quitté le chat",
            "created_at": datetime.utcnow().strftime("%H:%M"),
            "system": True,
        },
        room=room,
    )


@socketio.on("send_message")
def on_send_message(data):
    username = (data.get("username") or "Anonyme").strip()[:40]
    content = (data.get("content") or "").strip()[:1000]
    room = data.get("room", "general")

    if not content:
        return

    msg = Message(username=username, content=content, room=room)
    db.session.add(msg)
    db.session.commit()

    payload = msg.to_dict()
    emit("chat_message", payload, room=room)


# ---------------------------------------------------------------------------
# Init DB + seed
# ---------------------------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()
        if Project.query.count() == 0:
            demos = [
                Project(
                    titre="BudgetAI – Assistant de gestion budgétaire",
                    auteur="Nassim M.",
                    domaine="informatique",
                    annee="2025-2026",
                    description="Application Python + Streamlit pour suivre ses finances avec catégorisation intelligente.",
                    lien="https://github.com/NassimMaouche/tfe-hub",
                ),
                Project(
                    titre="SmartCampus – Gestion de salles",
                    auteur="Sarah K.",
                    domaine="web",
                    annee="2025-2026",
                    description="Plateforme web pour réserver et gérer les salles de cours en temps réel.",
                ),
                Project(
                    titre="DetectFraud – ML pour fraudes bancaires",
                    auteur="Yassine B.",
                    domaine="data",
                    annee="2024-2025",
                    description="Modèle de machine learning pour identifier les transactions suspectes.",
                ),
            ]
            db.session.add_all(demos)
            db.session.commit()
            print("✅ Base initialisée avec 3 projets de démo")


# Initialise la base au démarrage (local + Render/gunicorn)
init_db()

if __name__ == "__main__":
    print("🚀 TFE Hub Live démarré → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
