"""
TFE Hub Live – Version améliorée
================================
Base de données + Chat live + Likes + Recherche + Page détail
"""

from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "tfe_hub.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "tfe-hub-secret-change-me-in-prod"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")


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
    likes = db.Column(db.Integer, default=0)
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
            "likes": self.likes or 0,
            "created_at": self.created_at.strftime("%d/%m/%Y %H:%M") if self.created_at else "",
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
            "created_at": self.created_at.strftime("%H:%M") if self.created_at else "",
        }


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    auteur = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "auteur": self.auteur,
            "content": self.content,
            "created_at": self.created_at.strftime("%d/%m/%Y %H:%M") if self.created_at else "",
        }


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    domaine = request.args.get("domaine", "").strip()

    query = Project.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Project.titre.ilike(like),
                Project.description.ilike(like),
                Project.auteur.ilike(like),
            )
        )
    if domaine and domaine != "all":
        query = query.filter(Project.domaine == domaine)

    projects = query.order_by(Project.likes.desc(), Project.created_at.desc()).all()
    return render_template("index.html", projects=projects, q=q, domaine=domaine or "all")


@app.route("/projet/<int:project_id>")
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    comments = (
        Comment.query.filter_by(project_id=project_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return render_template("detail.html", project=project, comments=comments)


@app.route("/api/projects", methods=["GET"])
def api_projects():
    q = request.args.get("q", "").strip()
    domaine = request.args.get("domaine", "").strip()
    query = Project.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Project.titre.ilike(like),
                Project.description.ilike(like),
                Project.auteur.ilike(like),
            )
        )
    if domaine and domaine != "all":
        query = query.filter(Project.domaine == domaine)
    projects = query.order_by(Project.likes.desc(), Project.created_at.desc()).all()
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
        likes=0,
    )
    db.session.add(project)
    db.session.commit()
    socketio.emit("new_project", project.to_dict())
    return jsonify(project.to_dict()), 201


@app.route("/api/projects/<int:project_id>/like", methods=["POST"])
def api_like(project_id):
    project = Project.query.get_or_404(project_id)
    project.likes = (project.likes or 0) + 1
    db.session.commit()
    socketio.emit("project_liked", {"id": project.id, "likes": project.likes})
    return jsonify({"id": project.id, "likes": project.likes})


@app.route("/api/projects/<int:project_id>/comments", methods=["GET"])
def api_get_comments(project_id):
    comments = (
        Comment.query.filter_by(project_id=project_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return jsonify([c.to_dict() for c in comments])


@app.route("/api/projects/<int:project_id>/comments", methods=["POST"])
def api_add_comment(project_id):
    Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    auteur = (data.get("auteur") or "").strip()[:80]
    content = (data.get("content") or "").strip()[:1000]
    if not auteur or not content:
        return jsonify({"error": "Auteur et message obligatoires"}), 400
    comment = Comment(project_id=project_id, auteur=auteur, content=content)
    db.session.add(comment)
    db.session.commit()
    return jsonify(comment.to_dict()), 201


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
    emit("chat_message", msg.to_dict(), room=room)


@socketio.on("typing")
def on_typing(data):
    username = data.get("username", "")
    room = data.get("room", "general")
    emit("user_typing", {"username": username}, room=room, include_self=False)


def init_db():
    with app.app_context():
        db.create_all()
        try:
            db.session.execute(db.text("SELECT likes FROM projects LIMIT 1"))
        except Exception:
            try:
                db.session.execute(db.text("ALTER TABLE projects ADD COLUMN likes INTEGER DEFAULT 0"))
                db.session.commit()
            except Exception:
                db.session.rollback()

        if Project.query.count() == 0:
            demos = [
                Project(
                    titre="BudgetAI – Assistant de gestion budgétaire",
                    auteur="Nassim M.",
                    domaine="informatique",
                    annee="2025-2026",
                    description="Application Python + Streamlit pour suivre ses finances avec catégorisation intelligente et visualisations interactives.",
                    lien="https://github.com/NassimMaouche/tfe-hub",
                    likes=12,
                ),
                Project(
                    titre="SmartCampus – Gestion de salles",
                    auteur="Sarah K.",
                    domaine="web",
                    annee="2025-2026",
                    description="Plateforme web pour réserver et gérer les salles de cours en temps réel avec notifications.",
                    likes=8,
                ),
                Project(
                    titre="DetectFraud – ML pour fraudes bancaires",
                    auteur="Yassine B.",
                    domaine="data",
                    annee="2024-2025",
                    description="Modèle de machine learning pour identifier les transactions suspectes à partir de datasets réels.",
                    likes=15,
                ),
                Project(
                    titre="EcoRoute – Optimisation d’itinéraires verts",
                    auteur="Lina T.",
                    domaine="informatique",
                    annee="2025-2026",
                    description="Algorithme de plus court chemin prenant en compte l’empreinte carbone des trajets.",
                    likes=6,
                ),
            ]
            db.session.add_all(demos)
            db.session.commit()
            print("✅ Base initialisée avec projets de démo")


init_db()

if __name__ == "__main__":
    print("🚀 TFE Hub Live démarré → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
