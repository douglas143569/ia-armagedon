"""
ARMAGEDON — Vídeo narrado a partir de uma sequência de imagens

Para cada quadro: a narração vira voz (edge-tts online ou Piper offline), o quadro fica na tela
pelo tempo da fala com um movimento lento de câmera (zoom/panorâmica "Ken Burns"), o texto/balão
fica parado por cima, e os quadros se ligam com transição suave. Resultado: video.mp4 (H.264 + AAC).
"""

import asyncio
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image

import sequences

BASE_DIR = Path(__file__).resolve().parent
PIPER_MODEL = BASE_DIR / "models" / "pt_BR-faber-medium.onnx"

VOICES = {
    "francisca": {"name": "Francisca — feminina (online)", "edge": "pt-BR-FranciscaNeural"},
    "antonio": {"name": "Antônio — masculina (online)", "edge": "pt-BR-AntonioNeural"},
    "thalita": {"name": "Thalita — feminina (online)", "edge": "pt-BR-ThalitaMultilingualNeural"},
    "faber": {"name": "Faber — masculina (offline)", "piper": True},
}

SR = 24000            # taxa do áudio final
FPS = 30
XFADE = 0.6           # duração da transição entre quadros (s)
LEAD = 0.25           # silêncio antes de cada fala (s)
TAIL = 0.45           # silêncio depois de cada fala (s)
MIN_CLIP = 3.0        # quadro sem narração fica pelo menos isso na tela
MOTION_CLIP = 0.45    # quadros de "movimento" sem narração: ritmo de animação
LONGEST = 1080        # lado maior do vídeo

_piper = None


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg não encontrado. Instale com: winget install Gyan.FFmpeg")
    return exe


def run_ffmpeg(args, what):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ({what}): {r.stderr.strip()[-400:]}")

# ============================ VOZ ============================


def _decode_to_array(path):
    """Qualquer áudio → float32 mono em SR."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(path),
                        "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("não consegui decodificar o áudio")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def _edge(text, voice, rate):
    import edge_tts
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "voz.mp3"
        asyncio.run(edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(str(out)))
        return _decode_to_array(out)


def _piper_tts(text, rate):
    global _piper
    from piper import PiperVoice
    if _piper is None:
        _piper = PiperVoice.load(str(PIPER_MODEL))
    kwargs = {}
    try:
        from piper import SynthesisConfig
        kwargs["syn_config"] = SynthesisConfig(length_scale=1 / (1 + rate / 100))
    except Exception:
        pass
    chunks = list(_piper.synthesize(text, **kwargs))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
    src_sr = chunks[0].sample_rate
    idx = np.arange(0, len(audio), src_sr / SR)
    return np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)


def tts(text, voice="francisca", rate=0):
    """Texto → voz (float32 mono, SR). Se a voz online falhar, usa a offline."""
    v = VOICES.get(voice, VOICES["francisca"])
    if v.get("edge"):
        try:
            return _edge(text, v["edge"], rate), voice
        except Exception as e:
            print(f"⚠️  Voz online indisponível ({e}); usando a voz offline.")
    return _piper_tts(text, rate), "faber"


def speech_text(kind, frame):
    """O que é falado: a narração; sem narração, o texto do quadro (sem o 'Nome:' das falas da HQ)."""
    text = (frame.get("narration") or "").strip()
    if not text and kind != "movimento":
        text = (frame.get("text") or "").strip()
        if kind == "hq":
            text = re.sub(r"^\s*[^:]{1,24}:\s*", "", text)
    return re.sub(r"\s+", " ", text)

# ============================ VÍDEO ============================


def even_size(img):
    w, h = img.size
    s = LONGEST / max(w, h)
    return int(w * s) // 2 * 2, int(h * s) // 2 * 2


MOTIONS = [
    # zoom in no centro / zoom out / panorâmica da esquerda para a direita / da direita para a esquerda
    ("1+0.09*on/{D}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.09-0.09*on/{D}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.08", "(iw-iw/zoom)*on/{D}", "ih/2-(ih/zoom/2)"),
    ("1.08", "(iw-iw/zoom)*(1-on/{D})", "ih/2-(ih/zoom/2)"),
]


def render_clip(bg, layer, size, duration, motion, out):
    """Um quadro → clipe mp4 sem áudio: fundo com movimento lento + camada de texto parada por cima."""
    W, H = size
    frames = max(2, round(duration * FPS))
    with tempfile.TemporaryDirectory() as tmp:
        bg_path, layer_path = Path(tmp) / "bg.png", Path(tmp) / "layer.png"
        # fundo 2x maior: o zoompan fica suave, sem "tremidas"
        bg.convert("RGB").resize((W * 2, H * 2), Image.LANCZOS).save(bg_path)
        layer.save(layer_path)
        z, x, y = (part.replace("{D}", str(frames)) for part in MOTIONS[motion % len(MOTIONS)])
        filt = (f"[0:v]zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS}[bg];"
                f"[bg][1:v]overlay=0:0:format=auto,format=yuv420p[v]")
        run_ffmpeg(["-i", str(bg_path), "-loop", "1", "-i", str(layer_path), "-filter_complex", filt,
                    "-map", "[v]", "-frames:v", str(frames), "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)], "clipe")


def save_wav(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path if hasattr(path, "write") else str(path), "wb") as w:   # caminho ou arquivo em memória
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def build_video(seq_dir, ctx, voice="francisca", rate=0, progress=lambda f, m: None, cancelled=lambda: False):
    """Gera seq_dir/video.mp4 a partir dos quadros já prontos. Retorna (nome do arquivo, voz usada, duração)."""
    kind, frames = ctx["type"], ctx["plan"]["frames"]
    n = len(frames)
    raws = sequences.load_raws(seq_dir, n)
    if any(r is None for r in raws):
        raise RuntimeError("A sequência ainda não tem todos os quadros.")

    # 1) narração de cada quadro
    voices_used, speech = set(), []
    for i, f in enumerate(frames):
        if cancelled():
            raise InterruptedError()
        text = speech_text(kind, f)
        progress(0.02 + 0.28 * i / n, f"Gravando a narração {i + 1}/{n}...")
        if text:
            audio, used = tts(text, voice, rate)
            voices_used.add(used)
            speech.append(audio)
        else:
            speech.append(None)

    # 2) duração de cada quadro (o quadro dura o tempo da fala) e onde cada fala começa
    has_speech = any(a is not None and len(a) for a in speech)
    xfade = XFADE if has_speech or kind != "movimento" else 0.0
    durs, starts, offsets = [], [], []
    t = 0.0
    for i, a in enumerate(speech):
        lead = LEAD + (xfade / 2 if i else 0)
        if a is not None and len(a):
            d = lead + len(a) / SR + TAIL
        else:
            d = MOTION_CLIP if kind == "movimento" and not has_speech else MIN_CLIP
        if i < n - 1:
            d += xfade                     # a transição "come" o fim do quadro
        durs.append(d)
        starts.append(t)
        offsets.append(t + lead)
        t += d - (xfade if i < n - 1 else 0)
    total = t

    # 3) trilha de áudio: cada fala no seu lugar, normalizada
    track = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for a, off in zip(speech, offsets):
        if a is not None and len(a):
            s = int(off * SR)
            track[s:s + len(a)] += a[: len(track) - s]
    peak = float(np.max(np.abs(track))) or 1.0
    track *= 0.92 / peak
    fade = int(0.4 * SR)
    track[-fade:] *= np.linspace(1, 0, fade)

    # 4) um clipe por quadro (fundo em movimento + texto parado)
    size = even_size(raws[0])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clips = []
        for i, (raw, d) in enumerate(zip(raws, durs)):
            if cancelled():
                raise InterruptedError()
            progress(0.3 + 0.55 * i / n, f"Montando a cena {i + 1}/{n}...")
            layer = sequences.caption_layer(kind, size, frames[i].get("text", "") if ctx.get("captions") else "", i, n)
            motion = 0 if kind == "movimento" else i
            clip = tmp / f"clip_{i:02d}.mp4"
            render_clip(raw, layer, size, d, motion, clip)
            clips.append(clip)
        wav = tmp / "narracao.wav"
        save_wav(wav, track[: int(total * SR)])

        # 5) junta tudo com transições e põe a narração
        progress(0.88, "Juntando as cenas e o áudio...")
        args = []
        for c in clips:
            args += ["-i", str(c)]
        args += ["-i", str(wav)]
        if n == 1 or xfade == 0:
            chain = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
        else:
            parts, prev, acc = [], "[0:v]", 0.0
            for i in range(1, n):
                acc += durs[i - 1] - xfade
                out = f"[v{i}]" if i < n - 1 else "[v]"
                parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xfade}:offset={acc:.3f}{out}")
                prev = out
            chain = ";".join(parts)
        out = seq_dir / "video.mp4"
        run_ffmpeg([*args, "-filter_complex", chain, "-map", "[v]", "-map", f"{n}:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)], "vídeo final")
    return out.name, ", ".join(sorted(VOICES[v]["name"] for v in voices_used)) or "sem narração", round(total, 1)
