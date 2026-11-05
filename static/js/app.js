/**
 * TFE Hub Live – Frontend amélioré
 */

let socket = null;
let username = localStorage.getItem("tfe_username") || "";
let typingTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("project-form");
  if (form) form.addEventListener("submit", submitProject);

  const joinBtn = document.getElementById("join-btn");
  const usernameInput = document.getElementById("username-input");

  if (username && usernameInput) {
    usernameInput.value = username;
    joinChat();
  }

  if (joinBtn) joinBtn.addEventListener("click", joinChat);
  if (usernameInput) {
    usernameInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") joinChat();
    });
  }

  const chatForm = document.getElementById("chat-form");
  if (chatForm) chatForm.addEventListener("submit", sendMessage);

  const msgInput = document.getElementById("message-input");
  if (msgInput) {
    msgInput.addEventListener("input", () => {
      if (!socket || !username) return;
      socket.emit("typing", { username, room: "general" });
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
    if (!res.ok) throw new Error("Erreur serveur");
    form.reset();
    alert("✅ Projet publié avec succès !");
  } catch (err) {
    alert("Erreur lors de la publication : " + err.message);
  }
}

async function likeProject(id, btn) {
  try {
    const res = await fetch(`/api/projects/${id}/like`, { method: "POST" });
    const data = await res.json();
    const countEl = btn.querySelector(".like-count");
    if (countEl) countEl.textContent = data.likes;
  } catch (e) {
    console.error(e);
  }
}

function addProjectToList(p) {
  const list = document.getElementById("projects-list");
  if (!list) return;
  const empty = list.querySelector("p");
  if (empty) empty.remove();

  const card = document.createElement("article");
  card.className = "project-card bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-sm";
  card.dataset.id = p.id;
  card.innerHTML = `
    <div class="flex justify-between items-start mb-2 gap-2">
      <span class="badge badge-${p.domaine}">${p.domaine}</span>
      <span class="text-xs text-slate-400">${p.created_at || ""}</span>
    </div>
    <h3 class="font-bold text-base sm:text-lg mb-1 leading-snug">
      <a href="/projet/${p.id}" class="hover:text-primary-600">${escapeHtml(p.titre)}</a>
    </h3>
    <p class="text-sm text-slate-500 mb-3 line-clamp-2">${escapeHtml(p.description)}</p>
    <div class="flex justify-between items-center text-sm">
      <span class="font-medium text-slate-700">${escapeHtml(p.auteur)}</span>
      <div class="flex items-center gap-3">
        <button onclick="likeProject(${p.id}, this)" class="like-btn flex items-center gap-1 text-slate-500 hover:text-rose-500 transition">
          <span>❤️</span>
          <span class="like-count font-medium">${p.likes || 0}</span>
        </button>
        <a href="/projet/${p.id}" class="text-primary-600 hover:underline text-xs sm:text-sm">Voir →</a>
      </div>
    </div>
  `;
  list.prepend(card);

  const countEl = document.getElementById("project-count");
  if (countEl) {
    const n = list.querySelectorAll(".project-card").length;
    countEl.textContent = `${n} projet(s)`;
  }
}

function joinChat() {
  const input = document.getElementById("username-input");
  if (!input) return;
  username = (input.value || "").trim();
  if (!username) {
    alert("Choisis un pseudo");
    return;
  }
  localStorage.setItem("tfe_username", username);

  socket = io();

  socket.on("connect", () => {
    const status = document.getElementById("online-status");
    if (status) status.textContent = "● Connecté";
    socket.emit("join", { username, room: "general" });
  });

  socket.on("chat_message", (msg) => appendMessage(msg));
  socket.on("new_project", (project) => addProjectToList(project));

  socket.on("project_liked", (data) => {
    const card = document.querySelector(`.project-card[data-id="${data.id}"]`);
    if (card) {
      const el = card.querySelector(".like-count");
      if (el) el.textContent = data.likes;
    }
  });

  socket.on("user_typing", (data) => {
    const ind = document.getElementById("typing-indicator");
    if (!ind) return;
    ind.textContent = `${data.username} écrit...`;
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
    const messages = await res.json();
    messages.forEach(appendMessage);
  } catch (e) {
    console.error(e);
  }
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
    const isMine = msg.username === username;
    div.className = `chat-msg rounded-xl px-3 py-2 text-sm ${isMine ? "mine" : "other"}`;
    div.innerHTML = `
      <div class="font-semibold text-xs opacity-80 mb-0.5">${escapeHtml(msg.username)} · ${msg.created_at || ""}</div>
      <div>${escapeHtml(msg.content)}</div>
    `;
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
