const chat = document.querySelector("#chat");
const emptyState = document.querySelector("#empty-state");
const form = document.querySelector("#composer");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const notice = document.querySelector("#notice");
const voiceEnabled = document.querySelector("#voice-enabled");
const statusDot = document.querySelector("#status-dot");
const statusText = document.querySelector("#status-text");
const loginDialog = document.querySelector("#login-dialog");
const loginForm = document.querySelector("#login-form");
const tokenInput = document.querySelector("#token-input");
const loginError = document.querySelector("#login-error");

let token = localStorage.getItem("evaWebToken") || "";
let sending = false;

function authHeaders(extra) {
  return Object.assign({}, extra || {}, { Authorization: "Bearer " + token });
}

function showLogin() {
  if (!loginDialog.open) loginDialog.showModal();
}

function setNotice(text) {
  notice.textContent = text || "";
  notice.hidden = !text;
}

function setStatus(kind, text) {
  statusDot.className = "status-dot " + (kind || "");
  statusText.textContent = text;
}

function removeEmptyState() {
  if (emptyState && emptyState.isConnected) emptyState.remove();
}

function addMessage(role, text) {
  removeEmptyState();
  const item = document.createElement("article");
  item.className = "message " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text || "";
  item.appendChild(bubble);
  chat.appendChild(item);
  chat.scrollTop = chat.scrollHeight;
  return { item: item, bubble: bubble };
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

function lockComposer(value) {
  sending = value;
  input.disabled = value;
  send.disabled = value;
  setStatus(value ? "busy" : "online", value ? "EVA denkt …" : "EVA ist bereit");
}

async function api(path, options) {
  const config = Object.assign({}, options || {});
  config.headers = authHeaders(config.headers);
  const response = await fetch(path, config);
  if (response.status === 401) {
    localStorage.removeItem("evaWebToken");
    token = "";
    showLogin();
    throw new Error("Nicht autorisiert");
  }
  return response;
}

async function refreshStatus() {
  if (!token) {
    showLogin();
    return false;
  }
  try {
    const response = await api("/api/status");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    const ready = Boolean((data.voice && data.voice.ready) || !(data.voice && data.voice.enabled));
    const label = data.busy
      ? "EVA antwortet …"
      : ready ? "EVA ist bereit" : "Stimme wird geladen …";
    setStatus(data.busy ? "busy" : ready ? "online" : "", label);
    if (!data.browser_audio) {
      setNotice("Für Browser-Audio muss EVA_TTS_OUTPUT_FILE auf eine MP3- oder WAV-Datei zeigen.");
    }
    return true;
  } catch (error) {
    if (token) setStatus("", "EVA nicht erreichbar");
    return false;
  }
}

async function loadHistory() {
  const response = await api("/api/history");
  if (!response.ok) return;
  const data = await response.json();
  (data.messages || []).forEach(function (message) {
    addMessage(message.role, message.content);
  });
}

async function attachAudio(message, url) {
  if (!url) return;
  try {
    const response = await api(url);
    if (!response.ok) throw new Error("Audio nicht verfügbar");
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "auto";
    audio.src = objectUrl;
    audio.addEventListener("ended", function () {
      URL.revokeObjectURL(objectUrl);
    }, { once: true });
    message.item.appendChild(audio);
    if (voiceEnabled.checked) {
      audio.play().catch(function () {
        setNotice("EVAs Stimme ist bereit. Klicke im Beitrag auf Play.");
      });
    }
  } catch (error) {
    setNotice("EVAs Stimme konnte nicht geladen werden.");
  }
}

async function sendMessage(text) {
  lockComposer(true);
  setNotice("");
  addMessage("user", text);
  const assistant = addMessage("assistant", "");
  assistant.bubble.classList.add("streaming");

  try {
    const response = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    });
    if (response.status === 409) throw new Error("EVA bearbeitet bereits eine Anfrage.");
    if (!response.ok || !response.body) throw new Error("HTTP " + response.status);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let audioUrl = null;

    while (true) {
      const result = await reader.read();
      buffer += decoder.decode(result.value || new Uint8Array(), { stream: !result.done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      lines.forEach(function (line) {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === "delta") {
          assistant.bubble.textContent += event.text;
          chat.scrollTop = chat.scrollHeight;
        } else if (event.type === "done") {
          audioUrl = event.audio_url;
        } else if (event.type === "error") {
          throw new Error(event.error || "Unbekannter EVA-Fehler");
        }
      });
      if (result.done) break;
    }

    if (!assistant.bubble.textContent.trim()) {
      assistant.bubble.textContent = "Ich konnte gerade keine Antwort erzeugen.";
    }
    await attachAudio(assistant, audioUrl);
  } catch (error) {
    if (!assistant.bubble.textContent.trim()) {
      assistant.bubble.textContent = "Die Verbindung zu EVA ist gerade fehlgeschlagen.";
    }
    setNotice(error.message);
  } finally {
    assistant.bubble.classList.remove("streaming");
    lockComposer(false);
    input.focus();
  }
}

form.addEventListener("submit", function (event) {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || sending) return;
  input.value = "";
  resizeInput();
  sendMessage(text);
});

input.addEventListener("input", resizeInput);
input.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

loginForm.addEventListener("submit", async function (event) {
  event.preventDefault();
  token = tokenInput.value.trim();
  loginError.hidden = true;
  if (!token || !(await refreshStatus())) {
    loginError.hidden = false;
    return;
  }
  localStorage.setItem("evaWebToken", token);
  loginDialog.close();
  chat.replaceChildren();
  await loadHistory();
  if (!chat.children.length) chat.appendChild(emptyState);
  input.focus();
});

(async function boot() {
  resizeInput();
  if (await refreshStatus()) {
    await loadHistory();
    input.focus();
  }
  window.setInterval(refreshStatus, 15000);
})();
