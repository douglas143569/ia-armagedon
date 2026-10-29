#!/usr/bin/env python3
"""
ARMAGEDON — Assistente de Voz (estilo Alexa)

Fluxo:
  microfone sempre ouvindo → detector de fala (VAD) → Whisper (voz → texto)
  → "Armagedon" foi dito? → comando local (instantâneo) ou Ollama (perguntas)
  → Piper (texto → voz), falando frase por frase

Uso:
  python armagedon_voice.py                 assistente por voz
  python armagedon_voice.py --texto         digitar comandos (teste sem microfone)
  python armagedon_voice.py --dispositivos  listar microfones
  python armagedon_voice.py --mic 1         usar um microfone específico
  python armagedon_voice.py --modelo qwen2.5:3b
"""

import argparse
import ctypes
import difflib
import json
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata

import voice_director   # adapta o jeito de falar à emoção de quem ouve
import urllib.parse
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import numpy as np
    import requests
    import sounddevice as sd
    from faster_whisper import WhisperModel
    from piper import PiperVoice
except ImportError as e:
    print(f"❌ Dependência faltando: {e}")
    print("Execute: pip install faster-whisper piper-tts sounddevice numpy requests")
    sys.exit(1)

# ============================ CONFIGURAÇÃO ============================

BASE_DIR = Path(__file__).resolve().parent
PIPER_MODEL = BASE_DIR / "models" / "pt_BR-faber-medium.onnx"

WHISPER_MODEL = "base"        # "small" é mais preciso, mas ~4x mais lento neste PC
WHISPER_BEAM = 5
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"
HUB_URL = "http://localhost:3000"   # server.js (imagem, vídeo, voz)
API_PORT = 5003                     # API local usada pela página (via server.js)

WAKE_WORD = "armagedon"
WAKE_THRESHOLD = 0.8          # 0–1: semelhança mínima com "armagedon"
FOLLOW_UP_SECONDS = 6         # depois de responder, ouve mais um pouco sem precisar do nome
AWAKE_SECONDS = 7             # depois de "Armagedon" sozinho, espera o comando

SAMPLE_RATE = 16000
FRAME = 480                   # 30 ms
SILENCE_END_S = 0.8           # silêncio que encerra a frase
MAX_UTTERANCE_S = 15
MIN_UTTERANCE_S = 0.35
MIN_RMS = 0.006               # sensibilidade mínima do microfone

VOICE_LENGTH_SCALE = 0.95     # < 1 fala mais rápido, > 1 mais devagar
HISTORY_TURNS = 4             # trocas de mensagens lembradas na conversa

# Vocabulário que ajuda o Whisper a entender o nome e os comandos
WHISPER_PROMPT = (
    "Armagedon, que horas são? Que dia é hoje? Abre o YouTube. Abre o bloco de notas. "
    "Coloca um timer de 5 minutos. Me lembre de beber água em 10 minutos. "
    "Pesquisa na internet sobre. Gera uma imagem de. Aumenta o volume. Diminui o volume. Para."
)

SYSTEM_PROMPT = (
    "Você é o ARMAGEDON, um assistente de voz pessoal. Responda sempre em português do Brasil, "
    "de forma natural e direta, em no máximo 3 frases curtas, porque sua resposta será falada em voz alta. "
    "Nunca use markdown, listas, tabelas, emojis ou código. Escreva números e siglas como se fala. "
    "Agora são {agora}."
)

APPS = {
    "navegador": "https://www.google.com",
    "chrome": "chrome",
    "edge": "msedge",
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "explorador de arquivos": "explorer",
    "explorador": "explorer",
    "arquivos": "explorer",
    "pasta": "explorer",
    "meus documentos": "explorer shell:Personal",
    "downloads": "explorer shell:Downloads",
    "terminal": "wt",
    "prompt de comando": "cmd",
    "cmd": "cmd",
    "powershell": "powershell",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "configuracoes": "ms-settings:",
    "gerenciador de tarefas": "taskmgr",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "spotify": "spotify:",
    "camera": "microsoft.windows.camera:",
}

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "netflix": "https://www.netflix.com",
    "github": "https://github.com",
    "mapa": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "tradutor": "https://translate.google.com",
    "noticias": "https://news.google.com",
    "previsao do tempo": "https://www.google.com/search?q=previs%C3%A3o+do+tempo",
    "armagedon": HUB_URL,
    "painel": HUB_URL,
    "interface": HUB_URL,
    "plugins": HUB_URL + "/plugins",
}

ALUCINACOES = {
    "legendas pela comunidade amaraorg", "obrigado", "obrigada", "tchau", "inscrevase",
    "obrigado por assistir", "e ai", "legenda adriana zanotto",
}

# ============================ UTILITÁRIOS ============================


def norm(s: str) -> str:
    """minúsculas, sem acentos, só letras/números/espaços"""
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9: ]", " ", s)).strip()


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_wake(text: str):
    """Procura "Armagedon" nas 3 primeiras palavras. Retorna (achou, resto_do_texto)."""
    words = text.split()
    best = (0.0, None, None)
    for start in range(min(3, len(words))):
        for k in range(1, 4):
            if start + k > len(words):
                break
            letters = norm("".join(words[start:start + k])).replace(" ", "")
            if len(letters) < 5:
                continue
            score = similar(WAKE_WORD, letters)
            if score > best[0]:
                best = (score, start, k)
    if best[0] >= WAKE_THRESHOLD:
        rest = " ".join(words[best[1] + best[2]:]).strip(" ,.!?;:-")
        return True, rest
    return False, text


NUM_WORDS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40,
    "cinquenta": 50, "sessenta": 60, "noventa": 90, "cem": 100,
}
_NUM = r"(?:\d+|" + "|".join(NUM_WORDS) + r")"
# horário: "às 15 horas", "as 15:30", "às 7 e 45" (funciona com ou sem acento)
CLOCK_RE = r"\b[àa]s \d{1,2}(?:\s*(?::\s*\d{2}|horas?|h)\b)?(?:\s*e\s*\d{1,2}(?:\s*minutos?)?)?"
# duração dentro de uma frase: "em 10 minutos", "daqui a meia hora"
DURATION_PHRASE_RE = (r"\b(?:daqui a|daqui|dentro de|em)\s+(?:meia hora|(?:\S+\s+){0,3}?(?:segundos?|minutos?|horas?)"
                      r"(?:\s+e\s+\S+\s+(?:minutos?|segundos?))?)\b")


def to_number(expr: str) -> int:
    total = 0
    for part in re.split(r"\s+e\s+", expr.strip()):
        total += int(part) if part.isdigit() else NUM_WORDS.get(part, 0)
    return total


def parse_duration(n: str):
    """'1 hora e 30 minutos', 'cinco minutos', 'meia hora' → segundos (ou None)"""
    seconds = 0
    n = re.sub(CLOCK_RE, " ", n)  # "às 15 horas" é horário, não duração
    if re.search(r"\bmeia hora\b", n):
        seconds += 1800
    for num, unit in re.findall(rf"({_NUM}(?:\s+e\s+{_NUM})?)\s*(segundo|seg|minuto|min|hora|h)s?\b", n):
        value = to_number(num)
        seconds += value * {"seg": 1, "segundo": 1, "min": 60, "minuto": 60, "hora": 3600, "h": 3600}[unit]
    return seconds or None


def parse_clock(n: str):
    """'as 15 horas', 'as 15:30', 'as 7 e 45' → datetime futuro (ou None)"""
    m = re.search(r"\bas (\d{1,2})(?:\s*(?::|h|horas?)\s*(?:e\s*)?(\d{1,2})?|\s+e\s+(\d{1,2}))?\b", n)
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2) or m.group(3) or 0)
    if h > 23 or mi > 59:
        return None
    now = datetime.now()
    when = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    return when


def speak_duration(seconds: int) -> str:
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} hora" + ("s" if h > 1 else ""))
    if m:
        parts.append(f"{m} minuto" + ("s" if m > 1 else ""))
    if s:
        parts.append(f"{s} segundo" + ("s" if s > 1 else ""))
    return " e ".join(parts) or "0 segundos"


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#`>|~\[\]{}]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def log(icon: str, msg: str):
    print(f"[{datetime.now():%H:%M:%S}] {icon} {msg}", flush=True)


MEMORY_URL = "http://127.0.0.1:5004"   # memory_service.py (iniciado pelo server.js)


def memory_context(question):
    """O que a memória de longo prazo sabe de relevante para esta pergunta ('' se o serviço estiver fora)."""
    try:
        return requests.post(f"{MEMORY_URL}/context", json={"prompt": question, "channel": "voz"}, timeout=6).json().get("block", "")
    except Exception:
        return ""


def memory_emotion(question):
    """Análise emocional rápida da fala ({} se o serviço estiver fora)."""
    try:
        return requests.post(f"{MEMORY_URL}/emotion", json={"text": question, "deep": False}, timeout=4).json()
    except Exception:
        return {}


def memory_observe(question, answer):
    """Manda a troca para a memória aprender (em segundo plano no serviço)."""
    try:
        r = requests.post(f"{MEMORY_URL}/observe", json={"user": question, "assistant": answer, "channel": "voz"}, timeout=10)
        direct = r.json().get("direct")
        if direct:
            log("🧠", direct)
    except Exception:
        pass


def press_media_key(vk: int, times: int = 1):
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        time.sleep(0.01)


# ============================ ASSISTENTE ============================


class Armagedon:
    def __init__(self, mic=None, model=OLLAMA_MODEL, text_mode=False):
        self.model = model
        self.text_mode = text_mode
        self.mic = mic

        self.gen = 0                     # incrementa a cada interrupção (cancela fala/LLM antigos)
        self.tts_q = queue.Queue()
        self.utter_q = queue.Queue()
        self.speaking = False
        self.current_spoken = ""
        self.listen_until = 0.0          # janela em que não precisa dizer "Armagedon"
        self.history = deque(maxlen=HISTORY_TURNS * 2)
        self.timers = []
        self.listener_style = None   # jeito de falar adaptado à emoção de quem ouve (vale durante a resposta)
        self.running = True

        # Estado exposto para a página
        self.muted = False
        self.capturing = False
        self.transcribing = False
        self.thinking = False
        self.turn = 0
        self.events = deque(maxlen=300)
        self.event_id = 0
        self.events_lock = threading.Lock()

        log("🔥", "ARMAGEDON — Assistente de Voz")
        log("📥", f"Carregando voz Piper ({PIPER_MODEL.name})...")
        self.voice = PiperVoice.load(str(PIPER_MODEL))
        self.syn_config = None
        try:
            from piper import SynthesisConfig
            self.syn_config = SynthesisConfig(length_scale=VOICE_LENGTH_SCALE)
        except Exception:
            pass

        if not text_mode:
            log("📥", f"Carregando Whisper ({WHISPER_MODEL})...")
            self.whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

        threading.Thread(target=self._tts_loop, daemon=True).start()
        threading.Thread(target=self._warm_llm, daemon=True).start()

    # ---------------------------- fala ----------------------------

    def _synth(self, text, style=None):
        """style (voice_director.adapt_for_listener): fala mais lenta/suave, calma ou animada conforme quem ouve."""
        kwargs = {"syn_config": self.syn_config} if self.syn_config else {}
        if style and self.syn_config is not None:
            from piper import SynthesisConfig
            kwargs["syn_config"] = SynthesisConfig(length_scale=VOICE_LENGTH_SCALE / (1 + style["rate"] / 100))
        chunks = list(self.voice.synthesize(text, **kwargs))
        if not chunks:
            return None, 22050
        sr = chunks[0].sample_rate
        audio = np.concatenate([c.audio_float_array for c in chunks])
        if style:
            audio = np.clip(audio * 10 ** (style["volume"] / 40), -1, 1)
            extra = max(0, style["pause"] - 320)   # pausas maiores (ex.: com quem está ansioso)
            audio = np.concatenate([audio, np.zeros(int(sr * extra / 1000), dtype=audio.dtype)])
        return audio, sr

    @staticmethod
    def _tone(freqs, dur=0.09, sr=22050):
        parts = []
        for f in freqs:
            t = np.linspace(0, dur, int(sr * dur), False)
            env = np.minimum(1, np.minimum(t, dur - t) * 60)
            parts.append(0.25 * np.sin(2 * np.pi * f * t) * env)
        return np.concatenate(parts).astype(np.float32)

    def emit(self, kind, text):
        with self.events_lock:
            self.event_id += 1
            self.events.append({"id": self.event_id, "type": kind, "text": text,
                                "turn": self.turn, "ts": time.time()})

    def new_turn(self):
        self.turn += 1

    def say(self, text, style=None):
        text = clean_for_speech(text)
        if text:
            log("🗣️ ", text)
            self.thinking = False
            self.emit("assistant", text)
            self.tts_q.put(("text", (text, style or self.listener_style), self.gen))

    def beep(self, kind="wake"):
        freqs = {"wake": [880, 1320], "ok": [1320], "alarm": [1000, 0, 1000, 0, 1000]}[kind]
        self.tts_q.put(("tone", freqs, self.gen))

    def end_turn(self):
        """Marca o fim da resposta: abre a janela de continuação."""
        self.tts_q.put(("followup", None, self.gen))

    def _tts_loop(self):
        while True:
            kind, value, gen = self.tts_q.get()
            if gen != self.gen or kind == "followup":
                if kind == "followup" and gen == self.gen and not self.text_mode:
                    self.listen_until = time.time() + FOLLOW_UP_SECONDS
                if self.tts_q.empty():
                    self.speaking = False
                continue
            try:
                if kind == "text":
                    text, style = value
                    audio, sr = self._synth(text, style)
                    self.current_spoken = text
                else:
                    audio, sr = self._tone(value), 22050
                if audio is None or gen != self.gen:
                    continue
                self.speaking = True
                sd.play(audio, sr)
                stream = sd.get_stream()
                while stream.active:
                    if gen != self.gen:
                        sd.stop()
                        break
                    time.sleep(0.03)
            except Exception as e:
                log("⚠️ ", f"Erro no áudio: {e}")
            finally:
                if self.tts_q.empty():
                    self.speaking = False

    def interrupt(self):
        self.gen += 1
        try:
            sd.stop()
        except Exception:
            pass
        self.speaking = False

    # ---------------------------- ouvir ----------------------------

    def _audio_frames(self):
        """Gera frames de 30 ms a 16 kHz, mesmo se o microfone não suportar 16 kHz."""
        q = queue.Queue()

        def cb(indata, frames, t, status):
            q.put(indata[:, 0].copy())

        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                    blocksize=FRAME, device=self.mic, callback=cb)
            rate = SAMPLE_RATE
        except Exception:
            info = sd.query_devices(self.mic, "input")
            rate = int(info["default_samplerate"])
            stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                    blocksize=int(rate * 0.03), device=self.mic, callback=cb)
        buf = np.zeros(0, dtype=np.float32)
        with stream:
            log("🎙️ ", f"Microfone: {sd.query_devices(stream.device)['name']}")
            while self.running:
                block = q.get()
                if rate != SAMPLE_RATE:
                    idx = np.arange(0, len(block), rate / SAMPLE_RATE)
                    block = np.interp(idx, np.arange(len(block)), block).astype(np.float32)
                buf = np.concatenate([buf, block])
                while len(buf) >= FRAME:
                    yield buf[:FRAME]
                    buf = buf[FRAME:]

    def _listen_loop(self):
        """Detector de fala por energia com piso de ruído adaptativo."""
        frames = self._audio_frames()
        log("🤫", "Calibrando ruído ambiente (1 s)...")
        noise = float(np.mean([np.sqrt(np.mean(next(frames) ** 2)) for _ in range(33)])) + 1e-4
        preroll = deque(maxlen=10)
        speech, silence, voiced = [], 0, 0
        in_speech = False
        log("✅", 'Pronto! Diga "Armagedon" e o seu pedido.')

        for f in frames:
            rms = float(np.sqrt(np.mean(f ** 2)))
            factor = 5.0 if self.speaking else 3.0   # menos sensível enquanto ele fala (eco)
            thr = max(noise * factor, MIN_RMS)
            if not in_speech:
                preroll.append(f)
                if rms > thr:
                    voiced += 1
                else:
                    voiced = 0
                    noise = 0.97 * noise + 0.03 * rms
                if voiced >= 3 and not self.muted:
                    in_speech, speech, silence = True, list(preroll), 0
                    self.capturing = True
            else:
                speech.append(f)
                silence = 0 if rms > thr * 0.6 else silence + 1
                dur = len(speech) * FRAME / SAMPLE_RATE
                if silence * 0.03 >= SILENCE_END_S or dur >= MAX_UTTERANCE_S:
                    if dur - silence * 0.03 >= MIN_UTTERANCE_S:
                        self.utter_q.put(np.concatenate(speech))
                    in_speech, voiced = False, 0
                    self.capturing = False
                    preroll.clear()

    def transcribe(self, audio):
        segments, _ = self.whisper.transcribe(
            audio, language="pt", beam_size=WHISPER_BEAM, initial_prompt=WHISPER_PROMPT,
            hotwords="Armagedon", condition_on_previous_text=False, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments
                        if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0).strip()
        if norm(text).replace(" ", "") in {a.replace(" ", "") for a in ALUCINACOES}:
            return ""
        return text

    def _process_loop(self):
        while self.running:
            audio = self.utter_q.get()
            if self.muted:
                continue
            t0 = time.time()
            self.transcribing = True
            try:
                text = self.transcribe(audio)
            finally:
                self.transcribing = False
            if not text:
                continue
            awake = time.time() < self.listen_until
            found, rest = find_wake(text)

            # Eco da própria voz saindo da caixa de som
            if self.speaking and similar(norm(text), norm(self.current_spoken)) > 0.45:
                continue

            if self.speaking and not found:
                continue  # enquanto fala, só o nome interrompe
            if not found and not awake:
                log("··", f"(ignorado) {text}")
                continue

            log("👂", f"{text}   [{time.time() - t0:.1f}s]")
            if found:
                self.interrupt()
            command = rest if found else text
            if not command:
                self.wake()
                continue
            self.listen_until = 0
            self.new_turn()
            self.emit("user", command)
            self.handle(command)

    def wake(self):
        """Como dizer "Armagedon" sozinho: bip e espera o pedido."""
        self.interrupt()
        self.beep("wake")
        self.listen_until = time.time() + AWAKE_SECONDS

    # ---------------------------- comandos ----------------------------

    def handle(self, command):
        # Vários pedidos numa frase: "abre o YouTube e coloca um timer de 5 minutos"
        parts = re.split(
            r",?\s+e\s+(?=(?:abr|abe|coloc|p[õo]e|bot|pesquis|procur|ger|cri|me lembr|lembr|aument|diminu|abaix|sob))",
            command, flags=re.I)
        for part in parts:
            if part.strip():
                self._handle_one(part.strip())

    def _handle_one(self, command):
        n = norm(command)
        n = re.sub(r"^(?:por favor|ei|oi|ok)\s+", "", n)
        n = re.sub(r"\s+por favor$", "", n)

        # ---- parar / cancelar ----
        if re.match(r"^(?:para|pare|parar|chega|silencio|cala a boca|fica quieto|cancela|cancelar|esquece)\b", n):
            if re.search(r"\b(timer|timers|temporizador|lembrete|lembretes|alarme|alarmes|tudo)\b", n):
                count = self.cancel_timers()
                self.say(f"Cancelei {count} timer" + ("s" if count != 1 else "") + "." if count else "Não há timers ativos.")
            else:
                self.beep("ok")
            return

        # ---- sair ----
        if re.match(r"^(?:desliga|desligar|encerra|encerrar|fecha|fechar)\s+(?:o\s+)?assistente|^(?:tchau|ate logo|ate mais)$", n):
            self.say("Até logo. O Armagedon estará esperando.")
            time.sleep(3)
            self.running = False
            return

        # ---- hora ----
        if re.match(r"^(?:me (?:diz|fala) |voce sabe |sabe )?(?:que horas (?:sao|e)|que hora e|hora certa|horas)(?: agora)?$", n):
            now = datetime.now()
            h = now.hour
            hs = f"{h} hora" + ("s" if h != 1 else "")
            self.say(f"São {hs} em ponto." if now.minute == 0 else f"São {hs} e {now.minute} minuto" + ("s" if now.minute != 1 else "") + ".")
            self.end_turn()
            return

        # ---- data ----
        if re.match(r"^(?:que dia (?:e hoje|e|sao hoje)|qual (?:e )?a data(?: de hoje)?|que data e hoje|data de hoje|hoje e que dia|que dia da semana e hoje)$", n):
            dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
            meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                     "setembro", "outubro", "novembro", "dezembro"]
            d = datetime.now()
            self.say(f"Hoje é {dias[d.weekday()]}, {d.day} de {meses[d.month - 1]} de {d.year}.")
            self.end_turn()
            return

        # ---- volume ----
        if "volume" in n or re.search(r"\b(?:mais alto|mais baixo|muta|mutar|tira o som|sem som)\b", n):
            amount = re.search(r"(\d+)", n)
            presses = max(1, int(amount.group(1)) // 2) if amount else 10
            if re.search(r"\b(?:muta|mutar|mudo|tira o som|sem som|silencia)\b", n):
                press_media_key(0xAD)
                self.beep("ok")
            elif re.search(r"\b(?:aument\w*|sob\w*|mais alto|maximo|cima)\b", n):
                press_media_key(0xAF, 50 if "maximo" in n else presses)
                self.beep("ok")
            elif re.search(r"\b(?:diminu\w*|abaix\w*|baix\w*|mais baixo|minimo)\b", n):
                press_media_key(0xAE, 50 if "minimo" in n else presses)
                self.beep("ok")
            else:
                self.say("Quer que eu aumente ou diminua o volume?")
                self.end_turn()
            return

        # ---- lembrete ----
        if re.search(r"\b(?:me lembr\w*|lembr\w* me|lembrete|me avis\w*)\b", n):
            when = parse_clock(n)
            secs = parse_duration(n)
            if secs:
                when = datetime.now() + timedelta(seconds=secs)
            # o texto do lembrete sai da frase original, para manter os acentos
            what = re.sub(CLOCK_RE, " ", command.lower())
            what = re.sub(DURATION_PHRASE_RE, " ", what)
            what = re.sub(r"^.*?\b(?:me lembr\w*|lembr\w*[- ]me|lembrete|me avis\w*)\s*(?:de|do|da|que|pra|para)?\s*", "", what)
            what = re.sub(r"\s+", " ", what).strip(" .,!?")
            if not when:
                self.say("Para quando é o lembrete? Diga, por exemplo, em 10 minutos ou às 15 horas.")
                self.end_turn()
                return
            what = what or "o seu lembrete"
            self.add_timer((when - datetime.now()).total_seconds(), f"Lembrete: {what}.", f"lembrete '{what}'")
            self.say(f"Combinado. Vou te lembrar de {what} às {when:%H:%M}.")
            return

        # ---- timer ----
        secs = parse_duration(n)
        if secs and (re.search(r"\b(?:timer|taimer|tame|time|temporizador|cronometro|alarme|despertador|contagem)\b", n)
                     or re.match(r"^(?:coloc\w*|poe|bota|define|marca|inicia|liga|programa)\b", n)):
            label = speak_duration(secs)
            self.add_timer(secs, f"Seu timer de {label} terminou.", f"timer de {label}")
            self.say(f"Timer de {label} iniciado.")
            return

        # ---- gerar imagem ----
        m = re.search(r"\b(?:imagem|foto|desenho|figura|ilustracao|wallpaper)\b", n)
        if m and re.search(r"\b(?:ger\w*|cri\w*|desenh\w*|faz|faca|fazer|produz\w*)\b", n[:m.start()] + " "):
            prompt = re.search(r"(?:imagem|foto|desenho|figura|ilustração|ilustracao|wallpaper)\s+(?:de|do|da|dos|das|com|sobre|mostrando)?\s*(.+)",
                               command, flags=re.I)
            prompt = prompt.group(1).strip(" .!?") if prompt else ""
            if not prompt:
                self.say("O que você quer que eu desenhe?")
                self.end_turn()
                return
            self.generate_image(prompt)
            return

        # ---- pesquisar ----
        m = re.match(r"^(?:pesquis\w*|procur\w*|busc\w*|googl\w*|toca|tocar|coloca a musica|toque)\s+(.+)", command.strip(), flags=re.I) \
            if re.match(r"^(?:pesquis|procur|busc|googl|toca|toque|coloca a musica)", n) else None
        if m:
            query = m.group(1)
            on_youtube = bool(re.search(r"\b(?:no|na)\s+youtube\b", query, flags=re.I)) or n.startswith(("toca", "toque", "coloca a musica"))
            query = re.sub(r"\b(?:na internet|no google|na web|no youtube|na rede)\b", "", query, flags=re.I)
            query = re.sub(r"^\s*(?:sobre|por|pelo|pela|o que e|o que é)\s+", "", query, flags=re.I).strip(" .!?")
            if on_youtube:
                webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
            else:
                webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
            self.say(f"Pesquisando {query}" + (" no YouTube." if on_youtube else "."))
            return

        # ---- abrir programa / site ----
        m = re.match(r"^(?:abr\w*|abe\w*|inici\w*|execut\w*|entr[ae] n[oa]|vai (?:pro|para o|para a|pra)|mostra)\s+(?:o |a |os |as |meu |minha )?(.+)$", n)
        if m:
            self.open_target(m.group(1).strip())
            return

        # ---- pergunta livre → Ollama ----
        self.ask_llm(command)

    def open_target(self, target):
        target = re.sub(r"\b(?:pra mim|para mim|agora|ai)\b", "", target).strip()
        target = re.sub(r"^(?:o |a )?(?:site|pagina|programa|aplicativo|app)\s+(?:do |da |de )?", "", target)
        everything = {**SITES, **APPS}
        match = everything.get(target) or next(
            iter(difflib.get_close_matches(target, everything.keys(), n=1, cutoff=0.75)), None)
        if match and match in everything:
            match = everything[match]
        if not match:
            domain = re.sub(r"\s*ponto\s*", ".", target).replace(" ", "")
            if re.search(r"\.(com|br|net|org|io)\b", domain):
                match = "https://" + domain
        if not match:
            self.say(f"Não sei abrir {target} ainda. Você pode me ensinar no arquivo de configuração.")
            self.end_turn()
            return
        log("🚀", f"Abrindo {match}")
        if match.startswith("http"):
            webbrowser.open(match)
        else:
            subprocess.Popen(f'start "" {match}', shell=True)
        self.say(f"Abrindo {target}.")

    # ---------------------------- timers ----------------------------

    def add_timer(self, seconds, message, label):
        def fire():
            self.timers[:] = [t for t in self.timers if t[0] is not timer]
            log("⏰", message)
            self.new_turn()
            self.beep("alarm")
            self.say(message)
            self.beep("alarm")

        timer = threading.Timer(max(1, seconds), fire)
        timer.daemon = True
        timer.start()
        timer.fire_at = time.time() + max(1, seconds)
        self.timers.append((timer, label))
        log("⏱️ ", f"{label} → {datetime.now() + timedelta(seconds=seconds):%H:%M:%S}")

    def cancel_timers(self):
        count = len(self.timers)
        for timer, _ in self.timers:
            timer.cancel()
        self.timers.clear()
        return count

    # ---------------------------- imagem ----------------------------

    def generate_image(self, prompt):
        try:
            r = requests.post(f"{HUB_URL}/api/generate-image", json={"prompt": prompt, "turbo": True}, timeout=10)
            job = r.json().get("job_id")
            if not job:
                raise RuntimeError(r.json().get("error", "sem job_id"))
        except Exception as e:
            log("⚠️ ", f"Hub indisponível: {e}")
            self.say("O servidor do Armagedon não está rodando. Inicie o server ponto js e o gerador de imagens.")
            return
        self.say(f"Gerando uma imagem de {prompt}. Te aviso quando ficar pronta.")

        def watch():
            for _ in range(240):  # até 20 min
                time.sleep(5)
                try:
                    st = requests.get(f"{HUB_URL}/api/image-status/{job}", timeout=10).json()
                except Exception:
                    continue
                if st.get("status") in ("concluído", "erro", "cancelado"):
                    self.new_turn()
                if st.get("status") == "concluído":
                    self.beep("ok")
                    self.say(f"Sua imagem de {prompt} ficou pronta.")
                    return
                if st.get("status") in ("erro", "cancelado"):
                    self.say(f"A imagem de {prompt} não foi gerada: {st.get('error') or st.get('status')}.")
                    return

        threading.Thread(target=watch, daemon=True).start()

    # ---------------------------- Ollama ----------------------------

    def _warm_llm(self):
        try:
            requests.post(f"{OLLAMA_URL}/api/generate", timeout=300,
                          json={"model": self.model, "prompt": "", "keep_alive": "60m"})
            log("🧠", f"Modelo {self.model} carregado.")
        except Exception:
            log("⚠️ ", f"Ollama indisponível em {OLLAMA_URL} — só os comandos locais vão funcionar.")

    def ask_llm(self, question):
        gen = self.gen
        system = SYSTEM_PROMPT.format(agora=datetime.now().strftime("%A, %d/%m/%Y %H:%M"))
        memory = memory_context(question)
        if memory:
            system += "\n\n" + memory
        emotion = memory_emotion(question)
        if emotion.get("orientacao"):
            system += "\n\n" + emotion["orientacao"]
        high_risk = emotion.get("analise", {}).get("risco_emocional") == "Alto"
        # jeito de falar conforme a emoção de quem ouve (triste → suave e lento; ansioso → calmo, pausas maiores...)
        style = voice_director.adapt_for_listener(emotion.get("analise"))
        self.listener_style = style if style["tom"] != "natural" else None
        if self.listener_style:
            log("🎭", f"Falando com {style['tom']}")
        messages = [{"role": "system", "content": system}, *self.history, {"role": "user", "content": question}]
        log("🧠", "Pensando...")
        self.thinking = True
        full, buffer = "", ""
        try:
            with requests.post(f"{OLLAMA_URL}/api/chat", stream=True, timeout=(5, 300), json={
                "model": self.model, "messages": messages, "stream": True, "keep_alive": "60m",
                "options": {"temperature": 0.6, "num_predict": 220},
            }) as r:
                if r.status_code != 200:
                    raise RuntimeError(r.json().get("error", f"HTTP {r.status_code}"))
                for line in r.iter_lines():
                    if gen != self.gen:
                        self.thinking = False
                        return  # interrompido
                    if not line:
                        continue
                    piece = json.loads(line).get("message", {}).get("content", "")
                    full += piece
                    buffer += piece
                    # fala cada frase assim que fica pronta
                    while True:
                        m = re.search(r"[.!?…;:\n](\s|$)", buffer)
                        if not m or len(buffer[:m.end()].strip()) < 2:
                            break
                        self.say(buffer[:m.end()])
                        buffer = buffer[m.end():]
        except Exception as e:
            log("❌", f"Ollama: {e}")
            self.say("Não consegui falar com o meu cérebro, o Ollama. Verifique se ele está rodando.")
            return
        if buffer.strip():
            self.say(buffer)
        self.thinking = False
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": full})
        self.listener_style = None   # as frases desta resposta já levaram o estilo; o próximo turno começa neutro
        threading.Thread(target=memory_observe, args=(question, full), daemon=True).start()
        if high_risk and "188" not in full:   # garantia: o contato de apoio é sempre falado, mesmo se a IA esquecer
            self.say("Se você estiver pensando em se machucar, ligue agora para o CVV, no um oito oito. "
                     "É de graça, sigiloso e funciona vinte e quatro horas. Em perigo imediato, ligue um nove dois.")
        self.end_turn()

    # ---------------------------- API para a página ----------------------------

    def status(self):
        if self.muted:
            state = "mudo"
        elif self.speaking:
            state = "falando"
        elif self.thinking:
            state = "pensando"
        elif self.transcribing:
            state = "entendendo"
        elif self.capturing:
            state = "captando"
        elif time.time() < self.listen_until:
            state = "aguardando"
        else:
            state = "ouvindo"
        return {
            "state": state,
            "muted": self.muted,
            "model": self.model,
            "timers": [{"label": label, "in": max(0, round(t.fire_at - time.time()))} for t, label in self.timers],
            "last_event": self.event_id,
        }

    def events_since(self, since):
        with self.events_lock:
            return [e for e in self.events if e["id"] > since]

    def control(self, action, text=""):
        if action == "wake":
            self.wake()
        elif action == "mute":
            self.muted = True
            self.interrupt()
            self.listen_until = 0
        elif action == "unmute":
            self.muted = False
            self.beep("ok")
        elif action == "stop":
            self.interrupt()
        elif action == "command" and text.strip():
            self.interrupt()
            self.new_turn()
            self.emit("user", text.strip())
            threading.Thread(target=self.handle, args=(text.strip(),), daemon=True).start()
        elif action == "shutdown":
            self.interrupt()
            self.running = False
        else:
            return False
        return True

    def _start_api(self):
        assistant = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, payload):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self._send(200, {})

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/status":
                    self._send(200, assistant.status())
                elif parsed.path == "/events":
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "since" not in qs:  # primeira conexão: só informa o último id
                        self._send(200, {"events": [], "last": assistant.event_id})
                    else:
                        try:
                            since = int(qs["since"][0])
                        except ValueError:
                            since = 0
                        self._send(200, {"events": assistant.events_since(since), "last": assistant.event_id})
                else:
                    self._send(404, {"error": "não encontrado"})

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    data = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    data = {}
                if self.path == "/control":
                    ok = assistant.control(data.get("action", ""), data.get("text", ""))
                    self._send(200 if ok else 400, {"ok": ok, **assistant.status()})
                else:
                    self._send(404, {"error": "não encontrado"})

        try:
            server = ThreadingHTTPServer(("127.0.0.1", API_PORT), Handler)
        except OSError:
            log("⚠️ ", f"Porta {API_PORT} ocupada — o assistente já está aberto em outra janela?")
            return False
        threading.Thread(target=server.serve_forever, daemon=True).start()
        log("🔌", f"API para a página em http://127.0.0.1:{API_PORT}")
        return True

    # ---------------------------- execução ----------------------------

    def run(self):
        if self.text_mode:
            log("⌨️ ", "Modo texto: digite um comando (sem precisar dizer Armagedon). 'sair' encerra.")
            while self.running:
                try:
                    cmd = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if cmd.lower() in ("sair", "exit"):
                    break
                if cmd:
                    self.interrupt()
                    found, rest = find_wake(cmd)
                    self.handle(rest if found and rest else cmd)
            while self.speaking or not self.tts_q.empty():
                time.sleep(0.1)
            return

        if not self._start_api():
            return  # outra instância já está rodando; evita dois assistentes no mesmo microfone
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._process_loop, daemon=True).start()
        self.say("Armagedon online.")
        try:
            while self.running:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        log("👋", "Encerrado.")


def main():
    global WHISPER_MODEL
    ap = argparse.ArgumentParser(description="ARMAGEDON — assistente de voz")
    ap.add_argument("--texto", action="store_true", help="digitar comandos em vez de falar")
    ap.add_argument("--dispositivos", action="store_true", help="listar microfones e sair")
    ap.add_argument("--mic", type=int, default=None, help="índice do microfone")
    ap.add_argument("--modelo", default=OLLAMA_MODEL, help="modelo do Ollama")
    ap.add_argument("--whisper", default=WHISPER_MODEL, help="tiny | base | small")
    args = ap.parse_args()

    if args.dispositivos:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(f"{i:3d}  {d['name']}")
        return
    WHISPER_MODEL = args.whisper
    Armagedon(mic=args.mic, model=args.modelo, text_mode=args.texto).run()


if __name__ == "__main__":
    main()
