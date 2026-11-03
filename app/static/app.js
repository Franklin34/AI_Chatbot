const $ = (id) => document.getElementById(id);
const messagesEl = $("messages");
const input = $("input");
const sendBtn = $("send");
const stopBtn = $("stop");

const STORAGE_KEY = "chatbot.conversation_id";
const SUGGESTIONS = [
  "Explain how streaming responses work",
  "Write a Python function to merge two sorted lists",
  "Give me a 3-day itinerary for Lisbon",
];
const SPARKLE =
  '<svg viewBox="0 0 32 32" width="{s}" height="{s}"><path d="M16 5l2.8 8.2L27 16l-8.2 2.8L16 27l-2.8-8.2L5 16l8.2-2.8z" fill="currentColor"/></svg>';
const sparkle = (s) => SPARKLE.replaceAll("{s}", s);

// localStorage can throw (private mode, blocked site data), so it is optional.
const storage = {
  get() { try { return localStorage.getItem(STORAGE_KEY); } catch { return null; } },
  set(v) { try { v ? localStorage.setItem(STORAGE_KEY, v) : localStorage.removeItem(STORAGE_KEY); } catch {} },
};

let conversationId = storage.get();
let controller = null;
let busy = false;

function renderMarkdown(el, text) {
  if (window.marked && window.DOMPurify) {
    el.innerHTML = DOMPurify.sanitize(marked.parse(text, { breaks: true }));
  } else {
    el.textContent = text; // CDN unavailable: degrade to plain text
    el.style.whiteSpace = "pre-wrap";
  }
}

// Adds a header (language + copy button) and syntax highlighting to code blocks.
function decorate(el) {
  el.querySelectorAll("pre").forEach((pre) => {
    if (pre.dataset.done) return;
    pre.dataset.done = "1";
    const code = pre.querySelector("code");
    const lang = code?.className.match(/language-([\w+-]+)/)?.[1] ?? "text";
    if (code && window.hljs) { try { hljs.highlightElement(code); } catch {} }

    const bar = document.createElement("div");
    bar.className = "code-bar";
    const label = document.createElement("span");
    label.textContent = lang;
    const btn = document.createElement("button");
    btn.className = "copy";
    btn.type = "button";
    btn.textContent = "Copy";
    btn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(code?.innerText ?? pre.innerText);
        btn.textContent = "Copied ✓";
      } catch { btn.textContent = "Failed"; }
      setTimeout(() => (btn.textContent = "Copy"), 1500);
    };
    bar.append(label, btn);
    pre.prepend(bar);
  });
}

function scrollToBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }
function clearEmpty() { messagesEl.querySelector(".empty")?.remove(); }

// Returns the message element; `.row` points to its wrapper so it can be removed whole.
function addMessage(role, text = "") {
  clearEmpty();
  const row = document.createElement("div");
  row.className = `row ${role}`;
  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerHTML = sparkle(16);
    row.appendChild(avatar);
  }
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.row = row;
  if (role === "bot") {
    if (text) { renderMarkdown(el, text); decorate(el); }
    else el.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>';
  } else {
    el.textContent = text;
  }
  row.appendChild(el);
  messagesEl.appendChild(row);
  scrollToBottom();
  return el;
}

function notice(text) {
  clearEmpty();
  const el = document.createElement("div");
  el.className = "notice";
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollToBottom();
}

function showEmpty() {
  messagesEl.innerHTML = "";
  const box = document.createElement("div");
  box.className = "empty";
  box.innerHTML = `<div class="logo">${sparkle(28)}</div><h2>How can I help today?</h2><p>Ask a question, or try one of these.</p>`;
  const chips = document.createElement("div");
  chips.className = "chips";
  for (const s of SUGGESTIONS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = s;
    b.onclick = () => submit(s);
    chips.appendChild(b);
  }
  box.appendChild(chips);
  messagesEl.appendChild(box);
}

function setBusy(v) {
  busy = v;
  sendBtn.hidden = v;
  stopBtn.hidden = !v;
}

async function send(text) {
  setBusy(true);
  addMessage("user", text);
  const bubble = addMessage("bot");
  bubble.classList.add("typing");
  let raw = "";
  let pending = false;
  let finished = false;
  const paint = () => {
    pending = false;
    if (finished) return; // the final render below already ran
    renderMarkdown(bubble, raw);
    scrollToBottom();
  };

  controller = new AbortController();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, conversation_id: conversationId }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : `Server error (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop();
      for (const frame of frames) {
        const event = /^event: (.*)$/m.exec(frame)?.[1];
        const data = JSON.parse(/^data: (.*)$/m.exec(frame)?.[1] || "{}");
        if (event === "start") {
          conversationId = data.conversation_id;
          storage.set(conversationId);
        } else if (event === "token") {
          raw += data.text;
          if (!pending) { pending = true; requestAnimationFrame(paint); }
        } else if (event === "error") {
          throw new Error(data.message);
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") notice(e.message || "Something went wrong. Please try again.");
  } finally {
    finished = true;
    bubble.classList.remove("typing");
    if (raw) { renderMarkdown(bubble, raw); decorate(bubble); } else { bubble.row.remove(); }
    controller = null;
    setBusy(false);
    input.focus();
  }
}

function submit(text) {
  text = text.trim();
  if (!text || busy) return;
  input.value = "";
  autosize();
  send(text);
}

function autosize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

async function restore() {
  if (!conversationId) return showEmpty();
  try {
    const res = await fetch(`/api/history/${conversationId}`);
    if (!res.ok) throw new Error("gone");
    const { messages } = await res.json();
    messagesEl.innerHTML = "";
    for (const m of messages) addMessage(m.role === "assistant" ? "bot" : "user", m.content);
  } catch {
    conversationId = null;
    storage.set(null);
    showEmpty();
  }
}

async function loadModel() {
  try {
    const info = await (await fetch("/api/health")).json();
    const badge = $("model");
    $("model-text").textContent = `${info.provider} · ${info.model}`;
    badge.classList.toggle("off", info.status === "unconfigured");
    badge.hidden = false;
    if (info.status === "unconfigured") notice(`No API key configured for ${info.provider}. Add it to .env and restart.`);
  } catch { /* badge is optional */ }
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); submit(input.value); });
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(input.value); }
});
stopBtn.addEventListener("click", () => controller?.abort());
$("reset").addEventListener("click", () => {
  controller?.abort();
  if (conversationId) fetch(`/api/reset/${conversationId}`, { method: "POST" }).catch(() => {});
  conversationId = null;
  storage.set(null);
  showEmpty();
  input.focus();
});

restore();
loadModel();
