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
    let msg = body.detail?.message || body.detail?.code || `Request failed (${res.status})`;
    if (typeof msg === "string" && (msg.includes("<!DOCTYPE") || msg.includes("<html") || msg.includes("HTTP 504") || msg.includes("HTTP 502"))) {
      return "Speech recognition service is temporarily unavailable. Please try again or type the place name.";
    }
    return msg;
  } catch {
    return "Speech recognition service is temporarily unavailable. Please try again or type the place name.";
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

let liveTranscript = "";
let liveSpeechRec = null;

function startLiveRecognition(lang) {
  liveTranscript = "";
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  try {
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = lang || "en-IN";
    rec.onresult = (e) => {
      let finalStr = "";
      for (let i = 0; i < e.results.length; i++) {
        finalStr += e.results[i][0].transcript;
      }
      if (finalStr.trim()) liveTranscript = finalStr.trim();
    };
    rec.onerror = (e) => {
      console.warn("Live speech fallback notice:", e.error);
    };
    rec.start();
    liveSpeechRec = rec;
  } catch (err) {
    console.warn("SpeechRecognition init error:", err);
  }
}

function stopLiveRecognition() {
  if (liveSpeechRec) {
    try { liveSpeechRec.stop(); } catch {}
    liveSpeechRec = null;
  }
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
  const langVal = ui.lang?.value || "en-IN";
  const sttLang = langVal === "hinglish" ? "hi-IN" : langVal;
  startLiveRecognition(sttLang);
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

let currentUtteranceId = 0;
let ttsInFlight = false;
let lastSpokenText = "";
let lastSpokenTime = 0;

async function speak(text, languageCode) {
  if (ui.speak && !ui.speak.checked) return;
  if (!text || !text.trim()) return;

  const cleanText = text.trim();
  const now = Date.now();

  // Suppress immediate duplicate text within 2 seconds
  if (cleanText === lastSpokenText && (now - lastSpokenTime) < 2000) {
    return;
  }

  // Preempt any current audio cleanly
  stopAudio();

  const thisUtteranceId = ++currentUtteranceId;
  ttsInFlight = true;
  lastSpokenText = cleanText;
  lastSpokenTime = now;

  let played = false;
  try {
    const res = await fetch("/api/v1/speech/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: cleanText, language_code: languageCode, speed: 1.0 }),
    });

    if (thisUtteranceId !== currentUtteranceId) {
      return;
    }

    if (res.ok) {
      const url = URL.createObjectURL(await res.blob());
      if (thisUtteranceId !== currentUtteranceId) {
        URL.revokeObjectURL(url);
        return;
      }
      audioEl = new Audio(url);
      audioEl.onended = () => {
        URL.revokeObjectURL(url);
        if (thisUtteranceId === currentUtteranceId) {
          ttsInFlight = false;
          audioEl = null;
        }
      };
      audioEl.onerror = () => {
        URL.revokeObjectURL(url);
        if (thisUtteranceId === currentUtteranceId) {
          ttsInFlight = false;
          audioEl = null;
        }
      };
      await audioEl.play();
      played = true;
    }
  } catch (err) {
    console.warn("TTS synthesis error:", err);
  } finally {
    if (thisUtteranceId === currentUtteranceId && !played) {
      ttsInFlight = false;
    }
  }

  // Resilient fallback to browser Web Speech API
  if (!played && thisUtteranceId === currentUtteranceId && "speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(cleanText);
      u.lang = languageCode || "en-IN";
      ttsInFlight = true;
      u.onend = () => {
        if (thisUtteranceId === currentUtteranceId) {
          ttsInFlight = false;
        }
      };
      u.onerror = () => {
        if (thisUtteranceId === currentUtteranceId) {
          ttsInFlight = false;
        }
      };
      window.speechSynthesis.speak(u);
    } catch {
      ttsInFlight = false;
    }
  }
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
    active = { btn, html: btn.innerHTML, onText, out };
    const textSpan = btn.querySelector(".btn-text");
    const iconSpan = btn.querySelector(".btn-icon");
    if (textSpan && iconSpan) {
      textSpan.textContent = "Stop";
      iconSpan.textContent = "⏹️";
    } else {
      btn.textContent = "Stop";
    }
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
  const { btn, html, onText, out } = active;
  active = null;
  if (html) {
    btn.innerHTML = html;
  } else {
    btn.textContent = "Speak";
  }
  btn.classList.remove("rec");
  const duration = Date.now() - startedAt;
  mics.forEach((m) => { m.disabled = true; });
  try {
    stopLiveRecognition();
    const raw = await stopRecording();
    if (duration < MIN_RECORD_MS) {
      setStatus("Too short. Tap Speak and talk a little longer.", out);
      return;
    }
    setStatus("Transcribing...", out);
    const wav = await toWav16k(raw);
    const langVal = ui.lang?.value || "en-IN";
    const sttLang = langVal === "hinglish" ? "hi-IN" : langVal;
    let transcript = "";
    try {
      const res = await transcribe(wav, sttLang);
      transcript = (res?.transcript || "").trim();
    } catch (sttErr) {
      console.warn("Primary STT unavailable, using live speech fallback:", sttErr);
      if (liveTranscript) {
        transcript = liveTranscript;
      } else {
        throw sttErr;
      }
    }
    if (!transcript) {
      if (liveTranscript) {
        transcript = liveTranscript;
      } else {
        setStatus("I did not catch that. Please try again or type the place.", out);
        return;
      }
    }
    setStatus("", out);
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
  const inputEl = $(`${key}-input`);
  const b = document.createElement("button");
  b.type = "button";
  b.className = "mic-place-btn";
  b.setAttribute("aria-label", "Speak");
  b.innerHTML = '<span class="btn-text">Speak</span><span class="btn-icon">🎤</span>';
  b.title = "Say the place name. Uses the language chosen in the voice row below.";
  b.addEventListener("click", () => {
    const out = $("status");
    toggle(b, out, (text) => {
      $(`${key}-input`).value = text;
      searchBtn.click(); // shows candidates; you still pick one
    });
  });
  if (inputEl) {
    inputEl.after(b);
  } else {
    searchBtn.after(b);
  }
  mics.push(b);
}

function buildChatUi() {
  const anchor = document.querySelector(".chat");
  if (!anchor) return;
  const row = document.createElement("div");
  row.className = "row voice";

  const mic = document.createElement("button");
  mic.id = "mic-btn";
  mic.className = "chat-mic-btn";
  mic.setAttribute("aria-label", "Speak");
  mic.title = "Speak your question";
  mic.innerHTML = '<span class="btn-text">Speak</span><span class="btn-icon">🎙️</span>';
  mic.addEventListener("click", () =>
    toggle(mic, ui.status, (text) => {
      setStatus(`Heard: "${text}"`);
      const input = $("chat-input");
      if (input) {
        input.value = text;
        $("chat-send")?.click();
      }
    }));
  mics.push(mic);

  const sendBtn = $("chat-send");
  if (sendBtn) {
    sendBtn.before(mic);
  } else {
    anchor.appendChild(mic);
  }

  ui.lang = document.createElement("select");
  ui.lang.id = "voice-lang";
  for (const [val, label] of [
    ["kn-IN", "ಕನ್ನಡ - Kannada (unverified)"],
    ["hi-IN", "हिंदी (Hindi)"],
    ["hinglish", "हिंदी / English (Hinglish)"],
    ["en-IN", "English"],
  ]) {
    const o = document.createElement("option");
    o.value = val;
    o.textContent = label;
    ui.lang.appendChild(o);
  }
  ui.lang.value = "kn-IN"; // Default to authentic Bangalore Kannada
  ui.lang.addEventListener("change", () => {
    window.dispatchEvent(new CustomEvent("lang-changed", { detail: { lang: ui.lang.value } }));
  });

  const label = document.createElement("label");
  ui.speak = document.createElement("input");
  ui.speak.type = "checkbox";
  ui.speak.checked = true;
  label.append(ui.speak, document.createTextNode(" Speak answers"));

  row.append(ui.lang, label);
  ui.status = document.createElement("div");
  ui.status.id = "voice-status";
  anchor.after(row, ui.status);
}

window.addEventListener("nav-answer", async (e) => {
  if (ui.speak && !ui.speak.checked) return;
  const { text, lang } = e.detail;
  try {
    let ttsLang = "en-IN";
    if (lang === "kn") ttsLang = "kn-IN";
    else if (lang === "hinglish" || lang === "hi") ttsLang = "hi-IN";
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

function playChime() {
  try {
    const c = (window.__ac ||= new (window.AudioContext || window.webkitAudioContext)());
    c.resume();
    const t = c.currentTime, o = c.createOscillator(), g = c.createGain();
    o.frequency.setValueAtTime(880, t);
    o.frequency.setValueAtTime(1175, t + 0.12);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.35, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
    o.connect(g).connect(c.destination);
    o.start(t);
    o.stop(t + 0.4);
  } catch (err) {
    console.warn("Chime error:", err);
  }
}
window.playChime = playChime;

function playTurnChime() {
  playChime();
}

window.addEventListener("play-chime", () => {
  playChime();
});

function stopAudio() {
  currentUtteranceId++;
  ttsInFlight = false;
  if (audioEl) {
    try {
      audioEl.pause();
      audioEl.currentTime = 0;
    } catch {}
    audioEl = null;
  }
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch {}
  }
}

function isSpeaking() {
  return ttsInFlight || (audioEl && !audioEl.paused && !audioEl.ended) || ("speechSynthesis" in window && window.speechSynthesis.speaking);
}

export { speak, stopAudio, isSpeaking, playChime, playTurnChime, startRecording, stopRecording, toWav16k, transcribe };
