let socket = null;
let username = localStorage.getItem("tfe_username") || "";
let typingTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("project-form");
  if (form) form.addEventListener("submit", submitProject);

  const joinBtn = document.getElementById("join-btn");
  const usernameInput = document.getElementById("username-input");
  if (username && usernameInput && !usernameInput.value) usernameInput.value = username;
  if (usernameInput && usernameInput.value) {
    username = usernameInput.value;
    joinChat();
  }
  if (joinBtn) joinBtn.addEventListener("click", joinChat);
  if (usernameInput) usernameInput.addEventListener("keypress", e => { if (e.key === "Enter") joinChat(); });

  const chatForm = document.getElementById("chat-form");
  if (chatForm) chatForm.addEventListener("submit", sendMessage);

  const msgInput = document.getElementById("message-input");
  if (msgInput) msgInput.addEventListener("input", () => {
    if (socket && username) socket.emit("typing", { username, room: "general" });
  });
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
    alert("Projet publié.");
  } catch (err) {
    alert("Erreur lors de la publication.");
  }
}

async function likeProject(id, btn) {
  try {
    const res = await fetch(`/api/projects/${id}/like`, { method: "POST" });
    const data = await res.json();
    const el = btn.querySelector(".like-count");
    if (el) el.textContent = data.likes;
  } catch (e) {}
}

function addProjectToList(p) {
  const list = document.getElementById("projects-list");
  if (!list) return;
  const empty = list.querySelector("p");
  if (empty) empty.remove();
  const card = document.createElement("article");
  card.className = "project-card bg-white border border-slate-200 rounded-lg p-4 sm:p-5 hover:border-slate-300 transition";
  card.dataset.id = p.id;
  card.innerHTML = `
    <div class="flex items-start justify-between gap-3 mb-2">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="badge badge-${p.domaine}">${p.domaine}</span>
        <span class="text-xs text-slate-400">${p.created_at || ""}</span>
      </div>
      <button onclick="likeProject(${p.id}, this)" class="like-btn text-slate-400 hover:text-rose-500 text-sm flex items-center gap-1">
        <span>♥</span> <span class="like-count">${p.likes || 0}</span>
      </button>
    </div>
    <h3 class="font-semibold text-slate-900 mb-1">
      <a href="/projet/${p.id}" class="hover:text-sky-600">${esc(p.titre)}</a>
    </h3>
    <p class="text-sm text-slate-500 line-clamp-2 mb-3">${esc(p.description)}</p>
    <div class="flex items-center justify-between text-xs text-slate-400">
      <span>${esc(p.auteur)}</span>
      <a href="/projet/${p.id}" class="text-sky-600 hover:underline font-medium">Détails →</a>
    </div>`;
  list.prepend(card);
}

function joinChat() {
  const input = document.getElementById("username-input");
  if (!input) return;
  username = (input.value || "").trim();
  if (!username) { alert("Choisis un pseudo"); return; }
  localStorage.setItem("tfe_username", username);
  socket = io();
  socket.on("connect", () => {
    const s = document.getElementById("online-status");
    if (s) s.textContent = "● En ligne";
    socket.emit("join", { username, room: "general" });
  });
  socket.on("chat_message", appendMessage);
  socket.on("new_project", addProjectToList);
  socket.on("project_liked", (d) => {
    const card = document.querySelector(`.project-card[data-id="${d.id}"]`);
    if (card) { const el = card.querySelector(".like-count"); if (el) el.textContent = d.likes; }
  });
  socket.on("user_typing", (d) => {
    const ind = document.getElementById("typing-indicator");
    if (!ind) return;
    ind.textContent = d.username + " écrit…";
    ind.classList.remove("hidden");
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => ind.classList.add("hidden"), 2000);
  });
  document.getElementById("username-box")?.classList.add("hidden");
  document.getElementById("chat-input-box")?.classList.remove("hidden");
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
  const content = input?.value.trim();
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
    div.className = `chat-msg ${mine ? "mine" : "other"}`;
    div.innerHTML = `<div class="text-xs opacity-70 mb-0.5">${esc(msg.username)} · ${msg.created_at || ""}</div><div>${esc(msg.content)}</div>`;
  }
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
