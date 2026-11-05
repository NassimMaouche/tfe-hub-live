/**
 * TFE Hub Live – Frontend (SocketIO + API)
 */

let socket = null;
let username = localStorage.getItem("tfe_username") || "";

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("project-form").addEventListener("submit", submitProject);

  const joinBtn = document.getElementById("join-btn");
  const usernameInput = document.getElementById("username-input");

  if (username) {
    usernameInput.value = username;
    joinChat();
  }

  joinBtn.addEventListener("click", joinChat);
  usernameInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") joinChat();
  });

  document.getElementById("chat-form").addEventListener("submit", sendMessage);
});

// ---------- Projets ----------
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
    const project = await res.json();
    form.reset();
    alert("✅ Projet publié avec succès !");
  } catch (err) {
    alert("Erreur lors de la publication : " + err.message);
  }
}

function addProjectToList(p) {
  const list = document.getElementById("projects-list");
  const empty = list.querySelector("p");
  if (empty) empty.remove();

  const card = document.createElement("article");
  card.className = "project-card bg-white rounded-xl border border-slate-200 p-5 shadow-sm";
  card.innerHTML = `
    <div class="flex justify-between items-start mb-2">
      <span class="badge badge-${p.domaine}">${p.domaine}</span>
      <span class="text-xs text-slate-400">${p.created_at || ""}</span>
    </div>
    <h3 class="font-bold text-lg mb-1">${escapeHtml(p.titre)}</h3>
    <p class="text-sm text-slate-500 mb-3 line-clamp-2">${escapeHtml(p.description)}</p>
    <div class="flex justify-between items-center text-sm">
      <span class="font-medium">${escapeHtml(p.auteur)}</span>
      ${p.lien ? `<a href="${escapeHtml(p.lien)}" target="_blank" class="text-primary-600 hover:underline">Lien →</a>` : ""}
    </div>
  `;
  list.prepend(card);

  const countEl = document.getElementById("project-count");
  if (countEl) {
    const n = list.querySelectorAll(".project-card").length;
    countEl.textContent = `${n} projet(s)`;
  }
}

// ---------- Chat Live ----------
function joinChat() {
  const input = document.getElementById("username-input");
  username = (input.value || "").trim();
  if (!username) {
    alert("Choisis un pseudo");
    return;
  }
  localStorage.setItem("tfe_username", username);

  socket = io();

  socket.on("connect", () => {
    document.getElementById("online-status").textContent = "● Connecté";
    socket.emit("join", { username, room: "general" });
  });

  socket.on("chat_message", (msg) => {
    appendMessage(msg);
  });

  socket.on("new_project", (project) => {
    addProjectToList(project);
  });

  document.getElementById("username-box").classList.add("hidden");
  document.getElementById("chat-input-box").classList.remove("hidden");
  document.getElementById("chat-messages").innerHTML = "";
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
  const content = input.value.trim();
  if (!content || !socket) return;

  socket.emit("send_message", {
    username,
    content,
    room: "general",
  });
  input.value = "";
}

function appendMessage(msg) {
  const container = document.getElementById("chat-messages");
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
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
