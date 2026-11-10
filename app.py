"""
TFE Hub Live – version stable
Comptes obligatoires | Projets | Amis | Messages privés | Chat | Appels WebRTC
"""
import os
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, flash,
)
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "tfe_hub.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "tfe-hub-secret-change-me-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent", manage_session=True)


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

    def to_dict(self):
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "sender": self.sender.username if self.sender else "?",
            "content": self.content,
            "created_at": self.created_at.strftime("%d/%m %H:%M") if self.created_at else "",
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
            "id": self.id, "auteur": self.auteur, "content": self.content,
            "created_at": self.created_at.strftime("%d/%m/%Y %H:%M") if self.created_at else "",
        }


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Connecte-toi pour accéder au site.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapped


def current_user():
    uid = session.get("user_id")
    if uid:
        return db.session.get(User, uid)
    return None


def are_friends(a, b):
    return Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(
            db.and_(Friendship.requester_id == a, Friendship.addressee_id == b),
            db.and_(Friendship.requester_id == b, Friendship.addressee_id == a),
        ),
    ).first() is not None


def pm_room(a, b):
    x, y = sorted([a, b])
    return f"pm_{x}_{y}"


@app.context_processor
def inject_globals():
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
            errors.append("Pseudo : minimum 3 caractères.")
        if "@" not in email or "." not in email:
            errors.append("Email invalide.")
        if len(password) < 6:
            errors.append("Mot de passe : minimum 6 caractères.")
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
        session.clear()
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
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            flash(f"Bon retour, {user.username}.", "success")
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
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
    q = (request.args.get("q") or "").strip()
    domaine = (request.args.get("domaine") or "").strip()
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
    accepted = Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id),
    ).all()
    friends = [(f.addressee if f.requester_id == me.id else f.requester) for f in accepted]
    incoming = Friendship.query.filter_by(addressee_id=me.id, status="pending").all()
    outgoing = Friendship.query.filter_by(requester_id=me.id, status="pending").all()
    related = {me.id}
    for f in Friendship.query.filter(db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id)).all():
        related.add(f.requester_id)
        related.add(f.addressee_id)
    others = User.query.filter(~User.id.in_(related)).order_by(User.username).limit(40).all() if related else User.query.order_by(User.username).limit(40).all()
    return render_template("friends.html", friends=friends, incoming=incoming, outgoing=outgoing, others=others)


@app.route("/messages")
@app.route("/messages/<int:user_id>")
@login_required
def messages_page(user_id=None):
    me = current_user()
    accepted = Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id),
    ).all()
    friends = [(f.addressee if f.requester_id == me.id else f.requester) for f in accepted]
    peer = None
    history = []
    room = None
    if user_id:
        peer = User.query.get_or_404(user_id)
        if not are_friends(me.id, peer.id):
            flash("Vous devez être amis pour discuter en privé.", "warning")
            return redirect(url_for("friends_page"))
        history = PrivateMessage.query.filter(db.or_(
            db.and_(PrivateMessage.sender_id == me.id, PrivateMessage.receiver_id == peer.id),
            db.and_(PrivateMessage.sender_id == peer.id, PrivateMessage.receiver_id == me.id),
        )).order_by(PrivateMessage.created_at.asc()).limit(200).all()
        PrivateMessage.query.filter_by(sender_id=peer.id, receiver_id=me.id, is_read=False).update({"is_read": True})
        db.session.commit()
        room = pm_room(me.id, peer.id)
    return render_template("messages.html", friends=friends, peer=peer, history=history, room=room)


@app.route("/api/pm/<int:user_id>", methods=["POST"])
@login_required
def api_send_pm(user_id):
    me = current_user()
    if not are_friends(me.id, user_id):
        return jsonify({"error": "Pas amis"}), 403
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()[:2000]
    if not content:
        return jsonify({"error": "Message vide"}), 400
    pm = PrivateMessage(sender_id=me.id, receiver_id=user_id, content=content)
    db.session.add(pm)
    db.session.commit()
    payload = {
        "id": pm.id,
        "sender_id": me.id,
        "receiver_id": user_id,
        "sender": me.username,
        "content": content,
        "created_at": pm.created_at.strftime("%d/%m %H:%M") if pm.created_at else "",
    }
    room = pm_room(me.id, user_id)
    socketio.emit("pm_message", payload, room=room)
    socketio.emit("pm_message", payload, room=f"user_{user_id}")
    return jsonify(payload), 201


@app.route("/api/friends/request", methods=["POST"])
@login_required
def api_friend_request():
    me = current_user()
    data = request.get_json(silent=True) or {}
    target_id = data.get("user_id")
    if not target_id:
        uname = (data.get("username") or "").strip()
        target = User.query.filter_by(username=uname).first()
        if not target:
            return jsonify({"error": "Utilisateur introuvable"}), 404
        target_id = target.id
    target_id = int(target_id)
    if target_id == me.id:
        return jsonify({"error": "Impossible"}), 400
    if are_friends(me.id, target_id):
        return jsonify({"error": "Déjà amis"}), 400
    exists = Friendship.query.filter(db.or_(
        db.and_(Friendship.requester_id == me.id, Friendship.addressee_id == target_id),
        db.and_(Friendship.requester_id == target_id, Friendship.addressee_id == me.id),
    )).first()
    if exists:
        return jsonify({"error": "Demande déjà existante"}), 400
    fr = Friendship(requester_id=me.id, addressee_id=target_id, status="pending")
    db.session.add(fr)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/friends/accept", methods=["POST"])
@login_required
def api_friend_accept():
    me = current_user()
    data = request.get_json(silent=True) or {}
    fr = Friendship.query.get_or_404(data.get("id"))
    if fr.addressee_id != me.id or fr.status != "pending":
        return jsonify({"error": "Non autorisé"}), 403
    fr.status = "accepted"
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/friends/reject", methods=["POST"])
@login_required
def api_friend_reject():
    me = current_user()
    data = request.get_json(silent=True) or {}
    fr = Friendship.query.get_or_404(data.get("id"))
    if fr.addressee_id != me.id:
        return jsonify({"error": "Non autorisé"}), 403
    db.session.delete(fr)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/projects", methods=["POST"])
@login_required
def api_create_project():
    data = request.get_json(silent=True) or request.form
    user = current_user()
    titre = (data.get("titre") or "").strip()
    description = (data.get("description") or "").strip()
    domaine = (data.get("domaine") or "autre").strip()
    if not titre or not description:
        return jsonify({"error": "Titre et description obligatoires"}), 400
    project = Project(titre=titre, auteur=user.username, email=user.email, domaine=domaine,
        annee=(data.get("annee") or "").strip(), description=description,
        lien=(data.get("lien") or "").strip(), likes=0, user_id=user.id)
    db.session.add(project)
    db.session.commit()
    socketio.emit("new_project", project.to_dict())
    return jsonify(project.to_dict()), 201


@app.route("/api/projects/<int:pid>/like", methods=["POST"])
@login_required
def api_like(pid):
    project = Project.query.get_or_404(pid)
    project.likes = (project.likes or 0) + 1
    db.session.commit()
    socketio.emit("project_liked", {"id": project.id, "likes": project.likes})
    return jsonify({"id": project.id, "likes": project.likes})


@app.route("/api/projects/<int:pid>/comments", methods=["POST"])
@login_required
def api_comment(pid):
    Project.query.get_or_404(pid)
    data = request.get_json(silent=True) or {}
    user = current_user()
    content = (data.get("content") or "").strip()[:1000]
    if not content:
        return jsonify({"error": "Message vide"}), 400
    c = Comment(project_id=pid, auteur=user.username, content=content, user_id=user.id)
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route("/api/messages")
@login_required
def api_messages():
    room = request.args.get("room", "general")
    msgs = Message.query.filter_by(room=room).order_by(Message.created_at.desc()).limit(100).all()
    return jsonify([m.to_dict() for m in reversed(msgs)])


@socketio.on("connect")
def on_connect():
    uid = session.get("user_id")
    if uid:
        join_room(f"user_{uid}")
    emit("status", {"msg": "ok"})


@socketio.on("join")
def on_join(data):
    username = (data or {}).get("username") or session.get("username") or "Anonyme"
    room = (data or {}).get("room") or "general"
    join_room(room)
    emit("chat_message", {"username": "Système", "content": f"{username} a rejoint le chat",
         "created_at": datetime.utcnow().strftime("%H:%M"), "system": True}, room=room)


@socketio.on("send_message")
def on_send_message(data):
    data = data or {}
    username = (data.get("username") or session.get("username") or "Anonyme")[:40]
    content = (data.get("content") or "").strip()[:1000]
    room = data.get("room") or "general"
    if not content:
        return
    msg = Message(username=username, content=content, room=room)
    db.session.add(msg)
    db.session.commit()
    emit("chat_message", msg.to_dict(), room=room)


@socketio.on("typing")
def on_typing(data):
    data = data or {}
    emit("user_typing", {"username": data.get("username") or session.get("username") or ""},
         room=data.get("room") or "general", include_self=False)


@socketio.on("join_pm")
def on_join_pm(data):
    room = (data or {}).get("room")
    if room:
        join_room(room)


@socketio.on("pm_message")
def on_pm_message(data):
    me_id = session.get("user_id")
    if not me_id:
        return
    data = data or {}
    try:
        receiver_id = int(data.get("receiver_id") or 0)
    except (TypeError, ValueError):
        return
    content = (data.get("content") or "").strip()[:2000]
    if not content or not receiver_id:
        return
    if not are_friends(me_id, receiver_id):
        return
    pm = PrivateMessage(sender_id=me_id, receiver_id=receiver_id, content=content)
    db.session.add(pm)
    db.session.commit()
    payload = {
        "id": pm.id,
        "sender_id": me_id,
        "receiver_id": receiver_id,
        "sender": session.get("username") or "?",
        "content": content,
        "created_at": pm.created_at.strftime("%d/%m %H:%M") if pm.created_at else "",
    }
    room = pm_room(me_id, receiver_id)
    emit("pm_message", payload, room=room)
    emit("pm_message", payload, room=f"user_{receiver_id}")


@socketio.on("call_signal")
def on_call_signal(data):
    data = data or {}
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
        if Project.query.count() == 0:
            demos = [
                Project(titre="BudgetAI – Assistant budgétaire", auteur="Nassim M.", domaine="informatique",
                        annee="2025-2026", description="Application Python pour le suivi budgétaire.", likes=12),
                Project(titre="SmartCampus – Gestion de salles", auteur="Sarah K.", domaine="web",
                        annee="2025-2026", description="Plateforme web de réservation de salles.", likes=8),
                Project(titre="DetectFraud – ML fraudes bancaires", auteur="Yassine B.", domaine="data",
                        annee="2024-2025", description="Modèle ML pour détecter les transactions suspectes.", likes=15),
            ]
            db.session.add_all(demos)
            db.session.commit()


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"TFE Hub → http://0.0.0.0:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
