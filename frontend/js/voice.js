const $ = (id) => document.getElementById(id);
const MAX_RECORD_MS = 15000;
const MIN_RECORD_MS = 600;
const TARGET_RATE = 16000;

let recorder = null;
let stream = null;
let chunks = [];
let timer = null;
let startedAt = 0;
let busy = false;
let active = null; // { btn, label, onText, out }
let audioEl = null;
const ui = {};
const mics = [];

function setStatus(msg, el) {
  const target = el || ui.status;
  if (target) target.textContent = msg || "";
}

async function readError(res) {
  try {
    const body = await res.json();
    return body.detail?.message || body.detail?.code || `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buffer);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true);
  w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function toWav16k(blob) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  let decoded;
  try {
    decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  } finally {
    ctx.close();
  }
  const length = Math.max(1, Math.ceil(decoded.duration * TARGET_RATE));
  const off = new OfflineAudioContext(1, length, TARGET_RATE);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  const rendered = await off.startRendering();
  return encodeWav(rendered.getChannelData(0), TARGET_RATE);
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    throw new Error("This browser cannot record audio.");
  }
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.start();
  startedAt = Date.now();
}

function stopRecording() {
  return new Promise((resolve) => {
    const rec = recorder;
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      recorder = null;
      resolve(new Blob(chunks, { type: rec.mimeType }));
    };
    rec.stop();
  });
}

async function transcribe(wav, lang) {
  const fd = new FormData();
  fd.append("audio_file", wav, "clip.wav");
  fd.append("language_code", lang);
  let res;
  try {
    res = await fetch("/api/v1/speech/transcribe", { method: "POST", body: fd });
  } catch {
    throw new Error("Cannot reach the server");
  }
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

async function speak(text, languageCode) {
  let res;
  try {
    res = await fetch("/api/v1/speech/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language_code: languageCode, speed: 1.0 }),
    });
  } catch {
    throw new Error("Cannot reach the server");
  }
  if (!res.ok) throw new Error(await readError(res));
  const url = URL.createObjectURL(await res.blob());
  if (audioEl) audioEl.pause();
  audioEl = new Audio(url);
  audioEl.onended = () => URL.revokeObjectURL(url);
  await audioEl.play();
}

// One shared recorder: any mic button starts it, the same button stops it.
async function toggle(btn, out, onText) {
  if (busy) return;
  if (!active) {
    try {
      await startRecording();
    } catch (e) {
      setStatus(e.name === "NotAllowedError" ? "Microphone permission was denied." : e.message, out);
      return;
    }
    active = { btn, label: btn.textContent, onText, out };
    btn.textContent = "Stop";
    btn.classList.add("rec");
    setStatus("Listening... tap Stop when done (max 15 s)", out);
    timer = setTimeout(finish, MAX_RECORD_MS);
    return;
  }
  if (active.btn !== btn) {
    setStatus("Already recording. Tap Stop on the active mic first.", out);
    return;
  }
  await finish();
}

async function finish() {
  if (busy || !active) return;
  busy = true;
  clearTimeout(timer);
  const { btn, label, onText, out } = active;
  active = null;
  btn.textContent = label;
  btn.classList.remove("rec");
  const duration = Date.now() - startedAt;
  mics.forEach((m) => { m.disabled = true; });
  try {
    const raw = await stopRecording();
    if (duration < MIN_RECORD_MS) {
      setStatus("Too short. Tap Speak and talk a little longer.", out);
      return;
    }
    setStatus("Transcribing...", out);
    const wav = await toWav16k(raw);
    const { transcript } = await transcribe(wav, ui.lang.value);
    if (!transcript) {
      setStatus("I did not catch that. Please try again.", out);
      return;
    }
    onText(transcript);
  } catch (e) {
    setStatus(e.message || "Voice input failed.", out);
  } finally {
    busy = false;
    mics.forEach((m) => { m.disabled = false; });
  }
}

function addPlaceMic(key) {
  const searchBtn = $(`${key}-search`);
  if (!searchBtn) return;
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = "Speak";
  b.title = "Say the place name. Uses the language chosen in the voice row below.";
  b.addEventListener("click", () => {
    const out = $("status");
    toggle(b, out, (text) => {
      $(`${key}-input`).value = text;
      searchBtn.click(); // shows candidates; you still pick one
    });
  });
  searchBtn.after(b);
  mics.push(b);
}

function buildChatUi() {
  const anchor = document.querySelector(".chat");
  if (!anchor) return;
  const row = document.createElement("div");
  row.className = "row voice";

  const mic = document.createElement("button");
  mic.id = "mic-btn";
  mic.textContent = "Speak";
  mic.addEventListener("click", () =>
    toggle(mic, ui.status, (text) => {
      setStatus(`Heard: "${text}"`);
      $("chat-input").value = text;
      $("chat-send").click();
    }));
  mics.push(mic);

  ui.lang = document.createElement("select");
  ui.lang.id = "voice-lang";
  for (const [val, label] of [
    ["en-IN", "English / Hinglish"],
    ["hi-IN", "Hindi"],
    ["kn-IN", "Kannada"],
  ]) {
    const o = document.createElement("option");
    o.value = val;
    o.textContent = label;
    ui.lang.appendChild(o);
  }

  const label = document.createElement("label");
  ui.speak = document.createElement("input");
  ui.speak.type = "checkbox";
  ui.speak.checked = true;
  label.append(ui.speak, document.createTextNode(" Speak answers"));

  row.append(mic, ui.lang, label);
  ui.status = document.createElement("div");
  ui.status.id = "voice-status";
  anchor.after(row, ui.status);
}

window.addEventListener("nav-answer", async (e) => {
  if (!ui.speak?.checked) return;
  const { text, lang } = e.detail;
  try {
    let ttsLang = "en-IN";
    if (lang === "kn") ttsLang = "kn-IN";
    else if (lang === "hinglish") ttsLang = "hi-IN";
    await speak(text, ttsLang);
  } catch (err) {
    setStatus(`Could not speak: ${err.message}`);
  }
});

buildChatUi();
addPlaceMic("from");
addPlaceMic("to");

window.addEventListener("speak-text", async (e) => {
  const { text, lang } = e.detail;
  try {
    await speak(text, lang || "en-IN");
  } catch (err) {
    setStatus(`Could not speak: ${err.message}`);
  }
});

export { speak };
