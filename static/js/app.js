let socket = null;
let username = "";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("project-form");
  if (form) form.addEventListener("submit", submitProject);
  const joinBtn = document.getElementById("join-btn");
  const usernameInput = document.getElementById("username-input");
  if (joinBtn) joinBtn.addEventListener("click", joinChat);
  if (usernameInput) {
    usernameInput.addEventListener("keypress", (e) => { if (e.key === "Enter") joinChat(); });
  }
  const chatForm = document.getElementById("chat-form");
  if (chatForm) chatForm.addEventListener("submit", sendMessage);
  const msgInput = document.getElementById("message-input");
  if (msgInput) {
    msgInput.addEventListener("input", () => {
      if (socket && username) socket.emit("typing", { username, room: "general" });
    });
  }
});

async function submitProject(e) {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  try {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Erreur");
    form.reset();
    alert("Projet publié !");
    location.reload();
  } catch (err) {
    alert("Erreur lors de la publication.");
  }
}

async function likeProject(id, btn) {
  try {
    const res = await fetch("/api/projects/" + id + "/like", { method: "POST" });
    const data = await res.json();
    const el = btn.querySelector(".like-count");
    if (el) el.textContent = data.likes;
  } catch (e) {}
}

function joinChat() {
  const input = document.getElementById("username-input");
  if (!input) return;
  username = (input.value || "").trim();
  if (!username) { alert("Choisis un pseudo"); return; }
  socket = io();
  socket.on("connect", () => {
    const s = document.getElementById("online-status");
    if (s) s.textContent = "● En ligne";
    socket.emit("join", { username, room: "general" });
  });
  socket.on("chat_message", appendMessage);
  socket.on("new_project", () => location.reload());
  socket.on("project_liked", (d) => {
    const card = document.querySelector('.project[data-id="' + d.id + '"]');
    if (card) {
      const el = card.querySelector(".like-count");
      if (el) el.textContent = d.likes;
    }
  });
  socket.on("user_typing", (d) => {
    const ind = document.getElementById("typing-indicator");
    if (!ind) return;
    ind.style.display = "block";
    ind.textContent = (d.username || "") + " écrit…";
    clearTimeout(window._ty);
    window._ty = setTimeout(() => { ind.style.display = "none"; }, 2000);
  });
  document.getElementById("username-box").style.display = "none";
  const cf = document.getElementById("chat-form");
  if (cf) { cf.style.display = "flex"; }
  const msgs = document.getElementById("chat-messages");
  if (msgs) msgs.innerHTML = "";
  loadHistory();
}

async function loadHistory() {
  try {
    const res = await fetch("/api/messages?room=general");
    (await res.json()).forEach(appendMessage);
  } catch (e) {}
}

function sendMessage(e) {
  e.preventDefault();
  const input = document.getElementById("message-input");
  const content = (input && input.value || "").trim();
  if (!content || !socket) return;
  socket.emit("send_message", { username, content, room: "general" });
  input.value = "";
}

function appendMessage(msg) {
  const container = document.getElementById("chat-messages");
  if (!container) return;
  const div = document.createElement("div");
  if (msg.system) {
    div.className = "chat-msg system";
    div.textContent = msg.content;
  } else {
    const mine = msg.username === username;
    div.className = "chat-msg " + (mine ? "mine" : "other");
    div.innerHTML = '<div style="font-size:0.7rem;opacity:0.8;margin-bottom:2px">' +
      esc(msg.username) + " · " + (msg.created_at || "") + "</div><div>" + esc(msg.content) + "</div>";
  }
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
