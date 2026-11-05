"""
TFE Hub Live – Amis + messages privés + appels WebRTC
"""

from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, flash,
)
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "tfe_hub.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "tfe-hub-prod-secret-change-in-production-2026"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Friendship(db.Model):
    __tablename__ = "friendships"
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    addressee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    requester = db.relationship("User", foreign_keys=[requester_id])
    addressee = db.relationship("User", foreign_keys=[addressee_id])


class PrivateMessage(db.Model):
    __tablename__ = "private_messages"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    sender = db.relationship("User", foreign_keys=[sender_id])
    receiver = db.relationship("User", foreign_keys=[receiver_id])

    def to_dict(self):
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "sender": self.sender.username if self.sender else "?",
            "content": self.content,
            "created_at": self.created_at.strftime("%d/%m %H:%M") if self.created_at else "",
            "is_read": self.is_read,
        }


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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "titre": self.titre, "auteur": self.auteur,
            "domaine": self.domaine, "annee": self.annee or "",
            "description": self.description, "lien": self.lien or "",
            "likes": self.likes or 0,
            "created_at": self.created_at.strftime("%d/%m/%Y") if self.created_at else "",
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
            "id": self.id, "username": self.username, "content": self.content,
            "room": self.room,
            "created_at": self.created_at.strftime("%H:%M") if self.created_at else "",
        }


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    auteur = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "project_id": self.project_id, "auteur": self.auteur,
            "content": self.content,
            "created_at": self.created_at.strftime("%d/%m/%Y %H:%M") if self.created_at else "",
        }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Connecte-toi ou crée un compte pour accéder au site.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


def are_friends(uid1, uid2):
    return Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(
            db.and_(Friendship.requester_id == uid1, Friendship.addressee_id == uid2),
            db.and_(Friendship.requester_id == uid2, Friendship.addressee_id == uid1),
        ),
    ).first() is not None


def pm_room(uid1, uid2):
    a, b = sorted([uid1, uid2])
    return f"pm_{a}_{b}"


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        errors = []
        if len(username) < 3:
            errors.append("Le pseudo doit faire au moins 3 caractères.")
        if "@" not in email:
            errors.append("Email invalide.")
        if len(password) < 6:
            errors.append("Le mot de passe doit faire au moins 6 caractères.")
        if password != password2:
            errors.append("Les mots de passe ne correspondent pas.")
        if User.query.filter_by(username=username).first():
            errors.append("Ce pseudo est déjà pris.")
        if User.query.filter_by(email=email).first():
            errors.append("Cet email est déjà utilisé.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", username=username, email=email)
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        session["username"] = user.username
        flash(f"Bienvenue {user.username} !", "success")
        return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        login_id = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter(
            db.or_(User.username == login_id, User.email == login_id.lower())
        ).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            flash(f"Bon retour, {user.username}.", "success")
            return redirect(request.args.get("next") or url_for("index"))
        flash("Identifiants incorrects.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Tu es déconnecté.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    domaine = request.args.get("domaine", "").strip()
    query = Project.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Project.titre.ilike(like), Project.description.ilike(like), Project.auteur.ilike(like)))
    if domaine and domaine != "all":
        query = query.filter(Project.domaine == domaine)
    projects = query.order_by(Project.likes.desc(), Project.created_at.desc()).all()
    return render_template("index.html", projects=projects, q=q, domaine=domaine or "all")


@app.route("/projet/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    comments = Comment.query.filter_by(project_id=project_id).order_by(Comment.created_at.desc()).all()
    return render_template("detail.html", project=project, comments=comments)


@app.route("/amis")
@login_required
def friends_page():
    me = current_user()
    friendships = Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id),
    ).all()
    friends = [(f.addressee if f.requester_id == me.id else f.requester) for f in friendships]
    incoming = Friendship.query.filter_by(addressee_id=me.id, status="pending").all()
    outgoing = Friendship.query.filter_by(requester_id=me.id, status="pending").all()
    related_ids = {me.id}
    for f in Friendship.query.filter(db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id)).all():
        related_ids.add(f.requester_id)
        related_ids.add(f.addressee_id)
    others = User.query.filter(~User.id.in_(related_ids)).order_by(User.username).limit(50).all()
    return render_template("friends.html", friends=friends, incoming=incoming, outgoing=outgoing, others=others)


@app.route("/api/friends/request", methods=["POST"])
@login_required
def friend_request():
    me = current_user()
    data = request.get_json() or {}
    target_id = data.get("user_id")
    if not target_id:
        username = (data.get("username") or "").strip()
        target = User.query.filter_by(username=username).first()
        if not target:
            return jsonify({"error": "Utilisateur introuvable"}), 404
        target_id = target.id
    target_id = int(target_id)
    if target_id == me.id:
        return jsonify({"error": "Impossible"}), 400
    if are_friends(me.id, target_id):
        return jsonify({"error": "Déjà amis"}), 400
    existing = Friendship.query.filter(db.or_(
        db.and_(Friendship.requester_id == me.id, Friendship.addressee_id == target_id),
        db.and_(Friendship.requester_id == target_id, Friendship.addressee_id == me.id),
    )).first()
    if existing:
        return jsonify({"error": "Demande déjà existante"}), 400
    fr = Friendship(requester_id=me.id, addressee_id=target_id, status="pending")
    db.session.add(fr)
    db.session.commit()
    return jsonify({"ok": True, "id": fr.id})


@app.route("/api/friends/accept", methods=["POST"])
@login_required
def friend_accept():
    me = current_user()
    fr = Friendship.query.get_or_404((request.get_json() or {}).get("id"))
    if fr.addressee_id != me.id or fr.status != "pending":
        return jsonify({"error": "Non autorisé"}), 403
    fr.status = "accepted"
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/friends/reject", methods=["POST"])
@login_required
def friend_reject():
    me = current_user()
    fr = Friendship.query.get_or_404((request.get_json() or {}).get("id"))
    if fr.addressee_id != me.id:
        return jsonify({"error": "Non autorisé"}), 403
    db.session.delete(fr)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/messages")
@app.route("/messages/<int:user_id>")
@login_required
def messages_page(user_id=None):
    me = current_user()
    friendships = Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id),
    ).all()
    friends = [(f.addressee if f.requester_id == me.id else f.requester) for f in friendships]
    peer = None
    history = []
    if user_id:
        peer = User.query.get_or_404(user_id)
        if not are_friends(me.id, peer.id):
            flash("Tu dois être ami pour discuter en privé.", "warning")
            return redirect(url_for("friends_page"))
        history = PrivateMessage.query.filter(db.or_(
            db.and_(PrivateMessage.sender_id == me.id, PrivateMessage.receiver_id == peer.id),
            db.and_(PrivateMessage.sender_id == peer.id, PrivateMessage.receiver_id == me.id),
        )).order_by(PrivateMessage.created_at.asc()).limit(200).all()
        PrivateMessage.query.filter_by(sender_id=peer.id, receiver_id=me.id, is_read=False).update({"is_read": True})
        db.session.commit()
    return render_template("messages.html", friends=friends, peer=peer, history=history,
                           room=pm_room(me.id, peer.id) if peer else None)


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    if "user_id" not in session:
        return jsonify({"error": "Connexion requise"}), 401
    data = request.get_json() or request.form
    titre = (data.get("titre") or "").strip()
    description = (data.get("description") or "").strip()
    domaine = (data.get("domaine") or "autre").strip()
    user = current_user()
    auteur = user.username if user else (data.get("auteur") or "").strip()
    email = user.email if user else (data.get("email") or "").strip()
    if not titre or not auteur or not description:
        return jsonify({"error": "Champs obligatoires manquants"}), 400
    project = Project(titre=titre, auteur=auteur, email=email, domaine=domaine,
        annee=(data.get("annee") or "").strip(), description=description,
        lien=(data.get("lien") or "").strip(), likes=0, user_id=user.id if user else None)
    db.session.add(project)
    db.session.commit()
    socketio.emit("new_project", project.to_dict())
    return jsonify(project.to_dict()), 201


@app.route("/api/projects/<int:project_id>/like", methods=["POST"])
def api_like(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Connexion requise"}), 401
    project = Project.query.get_or_404(project_id)
    project.likes = (project.likes or 0) + 1
    db.session.commit()
    socketio.emit("project_liked", {"id": project.id, "likes": project.likes})
    return jsonify({"id": project.id, "likes": project.likes})


@app.route("/api/projects/<int:project_id>/comments", methods=["POST"])
def api_add_comment(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Connexion requise"}), 401
    Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    user = current_user()
    auteur = user.username if user else (data.get("auteur") or "").strip()[:80]
    content = (data.get("content") or "").strip()[:1000]
    if not auteur or not content:
        return jsonify({"error": "Auteur et message obligatoires"}), 400
    comment = Comment(project_id=project_id, auteur=auteur, content=content, user_id=user.id if user else None)
    db.session.add(comment)
    db.session.commit()
    return jsonify(comment.to_dict()), 201


@app.route("/api/messages")
def api_messages():
    room = request.args.get("room", "general")
    messages = Message.query.filter_by(room=room).order_by(Message.created_at.desc()).limit(100).all()
    return jsonify([m.to_dict() for m in reversed(messages)])


@socketio.on("connect")
def on_connect():
    emit("status", {"msg": "Connecté"})


@socketio.on("join")
def on_join(data):
    username = data.get("username", "Anonyme")
    room = data.get("room", "general")
    join_room(room)
    emit("chat_message", {"username": "Système", "content": f"{username} a rejoint le chat",
         "created_at": datetime.utcnow().strftime("%H:%M"), "system": True}, room=room)


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
    emit("user_typing", {"username": data.get("username", "")},
         room=data.get("room", "general"), include_self=False)


@socketio.on("join_pm")
def on_join_pm(data):
    room = data.get("room")
    if room:
        join_room(room)


@socketio.on("pm_message")
def on_pm_message(data):
    if "user_id" not in session:
        return
    me_id = session["user_id"]
    receiver_id = int(data.get("receiver_id", 0))
    content = (data.get("content") or "").strip()[:2000]
    if not content or not receiver_id or not are_friends(me_id, receiver_id):
        return
    pm = PrivateMessage(sender_id=me_id, receiver_id=receiver_id, content=content)
    db.session.add(pm)
    db.session.commit()
    emit("pm_message", pm.to_dict(), room=pm_room(me_id, receiver_id))


@socketio.on("call_signal")
def on_call_signal(data):
    target_id = data.get("target_id")
    if not target_id:
        return
    emit("call_signal", {
        "from_id": session.get("user_id"),
        "from_username": session.get("username"),
        "type": data.get("type"),
        "sdp": data.get("sdp"),
        "candidate": data.get("candidate"),
    }, room=f"user_{target_id}")


@socketio.on("join_user_room")
def on_join_user_room():
    uid = session.get("user_id")
    if uid:
        join_room(f"user_{uid}")


def init_db():
    with app.app_context():
        db.create_all()
        for col_sql in [
            "ALTER TABLE projects ADD COLUMN likes INTEGER DEFAULT 0",
            "ALTER TABLE projects ADD COLUMN user_id INTEGER",
            "ALTER TABLE comments ADD COLUMN user_id INTEGER",
        ]:
            try:
                db.session.execute(db.text(col_sql))
                db.session.commit()
            except Exception:
                db.session.rollback()
        if Project.query.count() == 0:
            demos = [
                Project(titre="BudgetAI – Assistant de gestion budgétaire", auteur="Nassim M.",
                        domaine="informatique", annee="2025-2026",
                        description="Application Python + Streamlit pour le suivi budgétaire.",
                        lien="https://github.com/NassimMaouche/tfe-hub", likes=12),
                Project(titre="SmartCampus – Gestion de salles", auteur="Sarah K.",
                        domaine="web", annee="2025-2026",
                        description="Plateforme web de réservation de salles.", likes=8),
                Project(titre="DetectFraud – Détection de fraudes par ML", auteur="Yassine B.",
                        domaine="data", annee="2024-2025",
                        description="Modèle ML pour identifier les transactions suspectes.", likes=15),
            ]
            db.session.add_all(demos)
            db.session.commit()


init_db()

if __name__ == "__main__":
    print("TFE Hub Live → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
