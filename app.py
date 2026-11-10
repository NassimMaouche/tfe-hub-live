"""TFE Hub Live - profil, PDF, notifications, favoris"""
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
PDF_DIR = UPLOAD_DIR / "pdfs"
AVATAR_DIR = UPLOAD_DIR / "avatars"
for d in (DATA_DIR, PDF_DIR, AVATAR_DIR):
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_PDF = {"pdf"}
ALLOWED_IMG = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "tfe-hub-secret-2026-nassim")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATA_DIR / 'tfe_hub.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent", manage_session=True)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    ecole = db.Column(db.String(120), default="")
    filiere = db.Column(db.String(120), default="")
    annee_etudes = db.Column(db.String(40), default="")
    bio = db.Column(db.Text, default="")
    avatar = db.Column(db.String(255), default="")
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
    pdf_file = db.Column(db.String(255), default="")
    likes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def to_dict(self):
        return {"id": self.id, "titre": self.titre, "auteur": self.auteur, "domaine": self.domaine, "annee": self.annee or "", "description": self.description, "lien": self.lien or "", "pdf_file": self.pdf_file or "", "likes": self.likes or 0, "views": self.views or 0, "created_at": self.created_at.strftime("%d/%m/%Y") if self.created_at else ""}

class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    auteur = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def to_dict(self):
        return {"id": self.id, "auteur": self.auteur, "content": self.content, "created_at": self.created_at.strftime("%d/%m/%Y %H:%M") if self.created_at else ""}

class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    room = db.Column(db.String(50), default="general")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def to_dict(self):
        return {"id": self.id, "username": self.username, "content": self.content, "created_at": self.created_at.strftime("%H:%M") if self.created_at else ""}

class Favorite(db.Model):
    __tablename__ = "favorites"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "project_id", name="uq_fav"),)

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), default="info")
    text = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(200), default="")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "text": self.text, "link": self.link or "", "is_read": self.is_read, "created_at": self.created_at.strftime("%d/%m %H:%M") if self.created_at else ""}

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    try:
        return db.session.get(User, uid)
    except Exception:
        return None

def are_friends(a, b):
    return Friendship.query.filter(Friendship.status == "accepted", db.or_(db.and_(Friendship.requester_id == a, Friendship.addressee_id == b), db.and_(Friendship.requester_id == b, Friendship.addressee_id == a))).first() is not None

def pm_room(a, b):
    x, y = sorted([int(a), int(b)])
    return f"pm_{x}_{y}"

def notify(user_id, text, kind="info", link=""):
    n = Notification(user_id=user_id, text=text, kind=kind, link=link)
    db.session.add(n)
    db.session.commit()
    try:
        socketio.emit("notification", n.to_dict(), room=f"user_{user_id}")
    except Exception:
        pass

def allowed_file(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed

def unread_count(uid):
    return Notification.query.filter_by(user_id=uid, is_read=False).count()

@app.context_processor
def inject_globals():
    u = current_user()
    return {"current_user": u, "notif_count": unread_count(u.id) if u else 0}

@app.before_request
def require_login_everywhere():
    if request.endpoint and str(request.endpoint).startswith("static"):
        return None
    if request.path.startswith("/uploads/"):
        return None
    if request.endpoint in ("login", "register"):
        return None
    if request.path.startswith("/socket.io"):
        return None
    if session.get("user_id"):
        u = current_user()
        if u:
            return None
        session.clear()
    if request.path.startswith("/api/"):
        return jsonify({"error": "Connexion requise"}), 401
    return redirect(url_for("login", next=request.path))

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
        if len(username) < 3: errors.append("Pseudo : minimum 3 caracteres.")
        if "@" not in email: errors.append("Email invalide.")
        if len(password) < 6: errors.append("Mot de passe : minimum 6 caracteres.")
        if password != password2: errors.append("Les mots de passe ne correspondent pas.")
        if User.query.filter_by(username=username).first(): errors.append("Ce pseudo est deja pris.")
        if User.query.filter_by(email=email).first(): errors.append("Cet email est deja utilise.")
        if errors:
            for e in errors: flash(e, "error")
            return render_template("register.html", username=username, email=email)
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session.clear()
        session["user_id"] = user.id
        session["username"] = user.username
        flash(f"Bienvenue {user.username} ! Complete ton profil.", "success")
        return redirect(url_for("profile_edit"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        login_id = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter(db.or_(User.username == login_id, User.email == login_id.lower())).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            flash(f"Bon retour, {user.username}.", "success")
            nxt = request.args.get("next") or url_for("index")
            if nxt in ("/login", "/register"): nxt = url_for("index")
            return redirect(nxt)
        flash("Identifiants incorrects.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Tu es deconnecte.", "success")
    return redirect(url_for("login"))

@app.route("/")
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
    me = current_user()
    fav_ids = {f.project_id for f in Favorite.query.filter_by(user_id=me.id).all()} if me else set()
    return render_template("index.html", projects=projects, q=q, domaine=domaine or "all", fav_ids=fav_ids)

@app.route("/projet/<int:project_id>")
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    project.views = (project.views or 0) + 1
    db.session.commit()
    comments = Comment.query.filter_by(project_id=project_id).order_by(Comment.created_at.desc()).all()
    me = current_user()
    is_fav = Favorite.query.filter_by(user_id=me.id, project_id=project_id).first() is not None if me else False
    owner = db.session.get(User, project.user_id) if project.user_id else None
    return render_template("detail.html", project=project, comments=comments, is_fav=is_fav, owner=owner)

@app.route("/profil")
@app.route("/profil/<int:user_id>")
def profile_view(user_id=None):
    me = current_user()
    user = me if user_id is None else User.query.get_or_404(user_id)
    projects = Project.query.filter_by(user_id=user.id).order_by(Project.created_at.desc()).all()
    return render_template("profile.html", profile=user, projects=projects, is_me=(user.id == me.id))

@app.route("/profil/edit", methods=["GET", "POST"])
def profile_edit():
    me = current_user()
    if request.method == "POST":
        me.ecole = (request.form.get("ecole") or "").strip()[:120]
        me.filiere = (request.form.get("filiere") or "").strip()[:120]
        me.annee_etudes = (request.form.get("annee_etudes") or "").strip()[:40]
        me.bio = (request.form.get("bio") or "").strip()[:500]
        f = request.files.get("avatar")
        if f and f.filename and allowed_file(f.filename, ALLOWED_IMG):
            ext = f.filename.rsplit(".", 1)[1].lower()
            name = secure_filename(f"u{me.id}_{int(datetime.utcnow().timestamp())}.{ext}")
            f.save(AVATAR_DIR / name)
            me.avatar = name
        db.session.commit()
        flash("Profil mis a jour.", "success")
        return redirect(url_for("profile_view"))
    return render_template("profile_edit.html", profile=me)

@app.route("/favoris")
def favorites_page():
    me = current_user()
    favs = Favorite.query.filter_by(user_id=me.id).order_by(Favorite.created_at.desc()).all()
    projects = [db.session.get(Project, f.project_id) for f in favs]
    projects = [p for p in projects if p]
    return render_template("favorites.html", projects=projects)

@app.route("/notifications")
def notifications_page():
    me = current_user()
    notifs = Notification.query.filter_by(user_id=me.id).order_by(Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(user_id=me.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("notifications.html", notifs=notifs)

@app.route("/amis")
def friends_page():
    me = current_user()
    accepted = Friendship.query.filter(Friendship.status == "accepted", db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id)).all()
    friends = [(f.addressee if f.requester_id == me.id else f.requester) for f in accepted]
    incoming = Friendship.query.filter_by(addressee_id=me.id, status="pending").all()
    outgoing = Friendship.query.filter_by(requester_id=me.id, status="pending").all()
    related = {me.id}
    for f in Friendship.query.filter(db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id)).all():
        related.add(f.requester_id); related.add(f.addressee_id)
    others = User.query.filter(~User.id.in_(related)).order_by(User.username).limit(50).all()
    return render_template("friends.html", friends=friends, incoming=incoming, outgoing=outgoing, others=others)

@app.route("/messages")
@app.route("/messages/<int:user_id>")
def messages_page(user_id=None):
    me = current_user()
    accepted = Friendship.query.filter(Friendship.status == "accepted", db.or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id)).all()
    friends = [(f.addressee if f.requester_id == me.id else f.requester) for f in accepted]
    peer = None; history = []; room = None
    if user_id is not None:
        peer = User.query.get_or_404(user_id)
        if peer.id == me.id:
            flash("Impossible.", "warning"); return redirect(url_for("messages_page"))
        if not are_friends(me.id, peer.id):
            flash("Vous devez etre amis.", "warning"); return redirect(url_for("friends_page"))
        history = PrivateMessage.query.filter(db.or_(db.and_(PrivateMessage.sender_id == me.id, PrivateMessage.receiver_id == peer.id), db.and_(PrivateMessage.sender_id == peer.id, PrivateMessage.receiver_id == me.id))).order_by(PrivateMessage.created_at.asc()).limit(300).all()
        PrivateMessage.query.filter_by(sender_id=peer.id, receiver_id=me.id, is_read=False).update({"is_read": True})
        db.session.commit()
        room = pm_room(me.id, peer.id)
    return render_template("messages.html", friends=friends, peer=peer, history=history, room=room)

@app.route("/uploads/pdfs/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)

@app.route("/uploads/avatars/<path:filename>")
def serve_avatar(filename):
    return send_from_directory(AVATAR_DIR, filename)

@app.route("/api/favorite/<int:pid>", methods=["POST"])
def api_favorite(pid):
    me = current_user()
    Project.query.get_or_404(pid)
    existing = Favorite.query.filter_by(user_id=me.id, project_id=pid).first()
    if existing:
        db.session.delete(existing); db.session.commit()
        return jsonify({"ok": True, "favorited": False})
    db.session.add(Favorite(user_id=me.id, project_id=pid)); db.session.commit()
    return jsonify({"ok": True, "favorited": True})

@app.route("/api/pm/<int:user_id>", methods=["POST"])
def api_send_pm(user_id):
    me = current_user()
    if not are_friends(me.id, user_id): return jsonify({"error": "Pas amis"}), 403
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()[:2000]
    if not content: return jsonify({"error": "Message vide"}), 400
    pm = PrivateMessage(sender_id=me.id, receiver_id=user_id, content=content)
    db.session.add(pm); db.session.commit()
    payload = {"id": pm.id, "sender_id": me.id, "receiver_id": user_id, "sender": me.username, "content": content, "created_at": pm.created_at.strftime("%d/%m %H:%M") if pm.created_at else ""}
    try:
        socketio.emit("pm_message", payload, room=pm_room(me.id, user_id))
        socketio.emit("pm_message", payload, room=f"user_{user_id}")
    except Exception: pass
    notify(user_id, f"{me.username} t'a envoye un message", kind="message", link=f"/messages/{me.id}")
    return jsonify(payload), 201

@app.route("/api/friends/request", methods=["POST"])
def api_friend_request():
    me = current_user()
    data = request.get_json(silent=True) or {}
    target_id = data.get("user_id")
    if not target_id:
        uname = (data.get("username") or "").strip()
        target = User.query.filter_by(username=uname).first()
        if not target: return jsonify({"error": "Utilisateur introuvable."}), 404
        target_id = target.id
    target_id = int(target_id)
    if target_id == me.id: return jsonify({"error": "Impossible"}), 400
    if are_friends(me.id, target_id): return jsonify({"error": "Deja amis"}), 400
    exists = Friendship.query.filter(db.or_(db.and_(Friendship.requester_id == me.id, Friendship.addressee_id == target_id), db.and_(Friendship.requester_id == target_id, Friendship.addressee_id == me.id))).first()
    if exists:
        if exists.status == "pending" and exists.addressee_id == me.id:
            exists.status = "accepted"; db.session.commit()
            notify(exists.requester_id, f"{me.username} a accepte ta demande d'ami", kind="friend", link="/amis")
            return jsonify({"ok": True, "accepted": True})
        return jsonify({"error": "Demande deja existante"}), 400
    fr = Friendship(requester_id=me.id, addressee_id=target_id, status="pending")
    db.session.add(fr); db.session.commit()
    notify(target_id, f"{me.username} t'a envoye une demande d'ami", kind="friend", link="/amis")
    return jsonify({"ok": True})

@app.route("/api/friends/accept", methods=["POST"])
def api_friend_accept():
    me = current_user()
    data = request.get_json(silent=True) or {}
    fr = Friendship.query.get_or_404(data.get("id"))
    if fr.addressee_id != me.id or fr.status != "pending": return jsonify({"error": "Non autorise"}), 403
    fr.status = "accepted"; db.session.commit()
    notify(fr.requester_id, f"{me.username} a accepte ta demande d'ami", kind="friend", link="/amis")
    return jsonify({"ok": True})

@app.route("/api/friends/reject", methods=["POST"])
def api_friend_reject():
    me = current_user()
    data = request.get_json(silent=True) or {}
    fr = Friendship.query.get_or_404(data.get("id"))
    if fr.addressee_id != me.id: return jsonify({"error": "Non autorise"}), 403
    db.session.delete(fr); db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/projects", methods=["POST"])
def api_create_project():
    me = current_user()
    titre = (request.form.get("titre") or "").strip()
    description = (request.form.get("description") or "").strip()
    domaine = (request.form.get("domaine") or "autre").strip()
    if not titre or not description: return jsonify({"error": "Titre et description obligatoires"}), 400
    pdf_name = ""
    f = request.files.get("pdf")
    if f and f.filename and allowed_file(f.filename, ALLOWED_PDF):
        ext = f.filename.rsplit(".", 1)[1].lower()
        pdf_name = secure_filename(f"p{me.id}_{int(datetime.utcnow().timestamp())}.{ext}")
        f.save(PDF_DIR / pdf_name)
    project = Project(titre=titre, auteur=me.username, email=me.email, domaine=domaine, annee=(request.form.get("annee") or "").strip(), description=description, lien=(request.form.get("lien") or "").strip(), pdf_file=pdf_name, likes=0, views=0, user_id=me.id)
    db.session.add(project); db.session.commit()
    socketio.emit("new_project", project.to_dict())
    return jsonify(project.to_dict()), 201

@app.route("/api/projects/<int:pid>/like", methods=["POST"])
def api_like(pid):
    project = Project.query.get_or_404(pid)
    project.likes = (project.likes or 0) + 1; db.session.commit()
    socketio.emit("project_liked", {"id": project.id, "likes": project.likes})
    return jsonify({"id": project.id, "likes": project.likes})

@app.route("/api/projects/<int:pid>/comments", methods=["POST"])
def api_comment(pid):
    project = Project.query.get_or_404(pid)
    me = current_user()
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()[:1000]
    if not content: return jsonify({"error": "Message vide"}), 400
    c = Comment(project_id=pid, auteur=me.username, content=content, user_id=me.id)
    db.session.add(c); db.session.commit()
    if project.user_id and project.user_id != me.id:
        notify(project.user_id, f"{me.username} a commente << {project.titre[:40]} >>", kind="comment", link=f"/projet/{pid}")
    return jsonify(c.to_dict()), 201

@app.route("/api/messages")
def api_messages():
    room = request.args.get("room", "general")
    msgs = Message.query.filter_by(room=room).order_by(Message.created_at.desc()).limit(100).all()
    return jsonify([m.to_dict() for m in reversed(msgs)])

@socketio.on("connect")
def on_connect():
    uid = session.get("user_id")
    if uid: join_room(f"user_{uid}")
    emit("status", {"msg": "ok"})

@socketio.on("join")
def on_join(data):
    username = (data or {}).get("username") or session.get("username") or "Anonyme"
    room = (data or {}).get("room") or "general"
    join_room(room)
    emit("chat_message", {"username": "Systeme", "content": f"{username} a rejoint le chat", "created_at": datetime.utcnow().strftime("%H:%M"), "system": True}, room=room)

@socketio.on("send_message")
def on_send_message(data):
    data = data or {}
    username = (data.get("username") or session.get("username") or "Anonyme")[:40]
    content = (data.get("content") or "").strip()[:1000]
    room = data.get("room") or "general"
    if not content: return
    msg = Message(username=username, content=content, room=room)
    db.session.add(msg); db.session.commit()
    emit("chat_message", msg.to_dict(), room=room)

@socketio.on("typing")
def on_typing(data):
    data = data or {}
    emit("user_typing", {"username": data.get("username") or session.get("username") or ""}, room=data.get("room") or "general", include_self=False)

@socketio.on("join_pm")
def on_join_pm(data):
    room = (data or {}).get("room")
    if room: join_room(room)

@socketio.on("pm_message")
def on_pm_message(data):
    me_id = session.get("user_id")
    if not me_id: return
    data = data or {}
    try: receiver_id = int(data.get("receiver_id") or 0)
    except (TypeError, ValueError): return
    content = (data.get("content") or "").strip()[:2000]
    if not content or not receiver_id or not are_friends(me_id, receiver_id): return
    pm = PrivateMessage(sender_id=me_id, receiver_id=receiver_id, content=content)
    db.session.add(pm); db.session.commit()
    payload = {"id": pm.id, "sender_id": me_id, "receiver_id": receiver_id, "sender": session.get("username") or "?", "content": content, "created_at": pm.created_at.strftime("%d/%m %H:%M") if pm.created_at else ""}
    emit("pm_message", payload, room=pm_room(me_id, receiver_id))
    emit("pm_message", payload, room=f"user_{receiver_id}")

@socketio.on("call_signal")
def on_call_signal(data):
    data = data or {}
    target_id = data.get("target_id")
    if not target_id: return
    emit("call_signal", {"from_id": session.get("user_id"), "from_username": session.get("username"), "type": data.get("type"), "sdp": data.get("sdp"), "candidate": data.get("candidate")}, room=f"user_{target_id}")

@socketio.on("join_user_room")
def on_join_user_room():
    uid = session.get("user_id")
    if uid: join_room(f"user_{uid}")

def init_db():
    with app.app_context():
        db.create_all()
        try:
            from sqlalchemy import text
            cols = {r[1] for r in db.session.execute(text("PRAGMA table_info(users)")).fetchall()}
            for col, typ in [("ecole", "VARCHAR(120)"), ("filiere", "VARCHAR(120)"), ("annee_etudes", "VARCHAR(40)"), ("bio", "TEXT"), ("avatar", "VARCHAR(255)")]:
                if col not in cols:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typ} DEFAULT ''"))
            pcols = {r[1] for r in db.session.execute(text("PRAGMA table_info(projects)")).fetchall()}
            if "pdf_file" not in pcols:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN pdf_file VARCHAR(255) DEFAULT ''"))
            if "views" not in pcols:
                db.session.execute(text("ALTER TABLE projects ADD COLUMN views INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        if Project.query.count() == 0:
            db.session.add_all([
                Project(titre="BudgetAI", auteur="Nassim M.", domaine="informatique", annee="2025-2026", description="Suivi budgetaire Python.", likes=12),
                Project(titre="SmartCampus", auteur="Sarah K.", domaine="web", annee="2025-2026", description="Reservation de salles.", likes=8),
                Project(titre="DetectFraud", auteur="Yassine B.", domaine="data", annee="2024-2025", description="ML fraudes bancaires.", likes=15),
            ])
            db.session.commit()

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
