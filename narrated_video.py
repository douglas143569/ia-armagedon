"""
ARMAGEDON — Vídeo narrado a partir de uma sequência de imagens

Para cada quadro: a narração vira voz (edge-tts online ou Piper offline), o quadro fica na tela
pelo tempo da fala com um movimento lento de câmera (zoom/panorâmica "Ken Burns"), o texto/balão
fica parado por cima, e os quadros se ligam com transição suave. Resultado: video.mp4 (H.264 + AAC).
"""

import asyncio
import json
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


def _edge(text, voice, rate, pitch=0, volume=0):
    """Voz online com prosódia: velocidade (%), altura (Hz) e volume (%)."""
    import edge_tts
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "voz.mp3"
        asyncio.run(edge_tts.Communicate(text, voice, rate=f"{int(rate):+d}%", pitch=f"{int(pitch):+d}Hz",
                                         volume=f"{int(volume):+d}%").save(str(out)))
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


DEEP_NOTE = ("\n\nObservação: este roteiro é de um vídeo inteiro. No campo roteiro_otimizado escreva só um resumo curto "
             "(as falas originais já estão guardadas); capriche nos personagens, na velocidade e no tom de cada um.")


def deep_llm():
    """Função que chama a IA para a direção profunda (o mesmo modelo do planejamento), ou None sem Ollama."""
    installed = sequences.ollama_models()
    model = next((m for m in sequences.PLAN_MODELS if m in installed), None)
    if not model:
        return None
    return lambda system, user: sequences.ask_json(model, system, user + DEEP_NOTE, 1200)


def _plain(text):
    """Para comparar falas: sem rubricas, aspas, pontuação e acentos."""
    import voice_director as vd
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text or "")
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", vd._norm(text))).strip()


def frame_script(kind, frame, narration_script=None):
    """Roteiro falado de um quadro, no formato do diretor de voz ("Nome: fala" / "Narrador: texto").
    narration_script: a narração do quadro já com o personagem de cada pedaço (ver voice_director.distribute_dialogue)."""
    import voice_director as vd
    raw = (frame.get("narration") or "").strip()
    narration = "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in raw.splitlines() if l.strip())   # mantém as linhas
    text = re.sub(r"\s+", " ", (frame.get("text") or "")).strip()
    if kind == "movimento":
        return narration_script or (f"Narrador: {narration}" if narration else "")
    if narration_script is not None:
        lines = [narration_script] if narration_script else []
    elif narration and vd.find_speaker_tags(narration):
        lines = [narration]                       # a narração já é um diálogo ("Nome: fala")
    else:
        lines = [f"Narrador: {narration}"] if narration else []
    is_line = bool(text and vd.find_speaker_tags(text) and vd.find_speaker_tags(text)[0][0] == 0)   # "Nome: fala"
    if narration_script is not None and kind == "hq":
        return "\n".join(lines)   # o roteiro inteiro já está na narração: o balão é só a parte visual (não repete)
    if text and (kind == "hq" or is_line):
        # fala ("Dom Pedro II: …") é dita pelo próprio personagem, em qualquer tipo de sequência;
        # se a narração já disse essa mesma fala, não repete
        speech = re.sub(r"^\s*[^:]{1,40}:\s*", "", text) if is_line else text
        already_said = _plain(speech) and _plain(speech) in _plain("\n".join(lines))
        if not already_said:
            lines.append(text if is_line else f"Narrador: {text}")
    elif not lines and text:
        lines.append(f"Narrador: {text}")
    return "\n".join(lines)


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

    # 1) narração dirigida de cada quadro: emoção, ritmo e pausas por trecho; nas HQs, uma voz por personagem
    import voice_director as vd
    # roteiro de diálogo repartido entre os quadros (às vezes no meio de uma fala): remonta quem fala cada pedaço
    distributed = vd.distribute_dialogue([f.get("narration") or "" for f in frames])
    scripts = [frame_script(kind, f, distributed[i] if distributed else None) for i, f in enumerate(frames)]
    all_segs = [seg for s in scripts for seg in vd.segment(s)]
    names = [who for who, _ in all_segs if who != vd.NARRATOR]
    # o mesmo elenco na sequência inteira; a ficha dos personagens e as falas ajudam a acertar o gênero da voz
    cast = vd.cast_voices(list(dict.fromkeys(names)), voice, vd.lines_by_speaker(all_segs),
                          ctx["plan"].get("characters", ""), ctx.get("voice_overrides"))
    ctx["cast"] = {k: VOICES.get(c["voice"], {}).get("name", c["voice"]) for k, c in cast.items()}

    # análise profunda (opcional): UMA direção da IA para o roteiro inteiro, repartida entre os quadros —
    # mais rápido que quadro a quadro e mantém cada personagem coerente do começo ao fim
    frame_segs = [None] * n
    ctx["voice_direction"] = "regras"
    if ctx.get("voice_deep") and any(scripts):
        progress(0.02, "🔬 Dirigindo as vozes com IA (análise profunda, ~2–4 min)...")
        llm = deep_llm()
        if llm:
            direction, segs_all, _, method = vd.direct_deep("\n".join(s for s in scripts if s), llm, voice, rate, cast=cast)
            k = 0
            for i, s in enumerate(scripts):
                count = len(vd.segment(s)) if s else 0
                frame_segs[i] = segs_all[k:k + count] or None
                k += count
            ctx["voice_direction"] = method
            (seq_dir / "direcao_voz.json").write_text(json.dumps(direction, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            ctx["voice_direction"] = "regras (Ollama indisponível para a análise profunda)"
        if cancelled():
            raise InterruptedError()

    voices_used, speech = set(), []
    for i, script in enumerate(scripts):
        if cancelled():
            raise InterruptedError()
        progress(0.1 + 0.2 * i / n, f"Gravando a narração {i + 1}/{n}...")
        if script:
            segs = frame_segs[i] or vd.direct(script, voice, rate, cast)[1]
            audio, used = vd.render(segs)
            voices_used |= used
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

    # 4–5) cenas em movimento + transições + narração
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "narracao.wav"
        save_wav(wav, track[: int(total * SR)])
        out = seq_dir / "video.mp4"
        assemble(seq_dir, ctx, raws, durs, xfade, total, out, progress, cancelled, audio=wav)
    shutil.copy2(out, seq_dir / NARRATED_MASTER)   # guarda a versão narrada (base para "música de fundo")
    import voice_director as vd
    names = sorted(vd.VOICES.get(v, {}).get("name", v) for v in voices_used)
    return out.name, ", ".join(names) or "sem narração", round(total, 1)


NARRATED_MASTER = "video_narrado.mp4"    # última versão com a narração automática
SILENT_MASTER = "video_sem_audio.mp4"    # versão sem áudio (base para unir um áudio seu)
USER_AUDIO_LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"


def assemble(seq_dir, ctx, raws, durs, xfade, total, out, progress, cancelled, audio=None, audio_filter=None):
    """Cenas → vídeo final: um clipe por quadro (fundo em movimento + texto parado), unidos com transição.
    audio: arquivo de áudio (ou None = vídeo sem áudio); audio_filter: filtro ffmpeg aplicado a ele ([a] na saída)."""
    kind, frames = ctx["type"], ctx["plan"]["frames"]
    n = len(raws)
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

        progress(0.88, "Juntando as cenas" + (" e o áudio..." if audio else "..."))
        args = []
        for c in clips:
            args += ["-i", str(c)]
        if n == 1 or xfade == 0:
            chain = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
        else:
            parts, prev, acc = [], "[0:v]", 0.0
            for i in range(1, n):
                acc += durs[i - 1] - xfade
                o = f"[v{i}]" if i < n - 1 else "[v]"
                parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xfade}:offset={acc:.3f}{o}")
                prev = o
            chain = ";".join(parts)
        maps = ["-map", "[v]"]
        if audio:
            args += ["-i", str(audio)]
            if audio_filter:
                chain += f";[{n}:a]{audio_filter}[a]"
                maps += ["-map", "[a]"]
            else:
                maps += ["-map", f"{n}:a"]
            enc_audio = ["-c:a", "aac", "-b:a", "160k"]
        else:
            enc_audio = ["-an"]
        run_ffmpeg([*args, "-filter_complex", chain, *maps,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    *enc_audio, "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)], "vídeo final")
    return out


def _timeline(n, each, xfade):
    """Duração de cada clipe para todos os quadros ficarem `each` segundos na tela (a transição come o fim)."""
    durs = [each + (xfade if i < n - 1 else 0) for i in range(n)]
    return durs, sum(durs) - xfade * (n - 1)


def _load_raws(seq_dir, ctx):
    raws = sequences.load_raws(seq_dir, len(ctx["plan"]["frames"]))
    if any(r is None for r in raws):
        raise RuntimeError("A sequência ainda não tem todos os quadros.")
    return raws


def build_silent_video(seq_dir, ctx, seconds_per_frame=4.0, progress=lambda f, m: None, cancelled=lambda: False):
    """Mesmas cenas, transições e textos do vídeo narrado, mas SEM áudio — para unir um áudio seu depois."""
    raws = _load_raws(seq_dir, ctx)
    n = len(raws)
    each = max(0.4 if ctx["type"] == "movimento" else 1.5, min(60.0, float(seconds_per_frame or 4)))
    xfade = 0.0 if ctx["type"] == "movimento" and each < 1.5 else min(XFADE, each / 3)
    durs, total = _timeline(n, each, xfade)
    out = seq_dir / SILENT_MASTER
    assemble(seq_dir, ctx, raws, durs, xfade, total, out, progress, cancelled)
    shutil.copy2(out, seq_dir / "video.mp4")
    return "video.mp4", "sem áudio", round(total, 1)


def attach_audio(seq_dir, ctx, audio_path, mode="ajustar", volume=1.0, progress=lambda f, m: None, cancelled=lambda: False):
    """Une um arquivo de áudio ao vídeo da sequência.
      ajustar — refaz as cenas para o vídeo ter a duração do áudio (cada quadro fica o mesmo tempo na tela)
      manter  — mantém o vídeo como está; o áudio é cortado (com fade) ou completado com silêncio
      fundo   — mantém a narração e põe o áudio por baixo, abaixando sozinho quando há fala (música de fundo)
    Retorna (arquivo, descrição do áudio, duração)."""
    audio_path = Path(audio_path)
    info = _probe(audio_path)
    if not info["has_audio"] or info["duration"] <= 0:
        raise RuntimeError("Não consegui ler o áudio desse arquivo.")
    A = info["duration"]
    vol = max(0.05, min(2.0, float(volume or 1.0)))
    out = seq_dir / "video.mp4"
    name = audio_path.name.split("_", 1)[-1] if audio_path.name.startswith("audio_") else audio_path.name

    if mode == "ajustar":
        raws = _load_raws(seq_dir, ctx)
        n = len(raws)
        xfade = 0.0 if ctx["type"] == "movimento" else XFADE
        each = max(1.0, (A + xfade * (n - 1) - xfade * (n - 1)) / n)   # cada quadro na tela: A/n segundos
        durs, total = _timeline(n, each, xfade)
        filt = (f"aresample={SR * 2},aformat=channel_layouts=stereo,volume={vol:.2f},{USER_AUDIO_LOUDNESS},"
                f"apad,atrim=0:{total:.3f},afade=t=out:st={max(0, total - 1.2):.2f}:d=1.2")
        assemble(seq_dir, ctx, raws, durs, xfade, total, out, progress, cancelled, audio=audio_path, audio_filter=filt)
        return out.name, f"arquivo: {name} (vídeo ajustado ao áudio)", round(total, 1)

    if mode == "fundo":
        base = seq_dir / NARRATED_MASTER
        if not base.exists():
            raise RuntimeError("Este vídeo não tem narração. Use “substituir o áudio”.")
        T = _probe(base)["duration"]
        progress(0.3, "Mixando o áudio por baixo da narração...")
        fc = (f"[1:a]aresample={SR * 2},aformat=channel_layouts=stereo,volume={0.35 * vol:.3f},"
              f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, T - 2.5):.2f}:d=2.5[m];"
              f"[0:a]aresample={SR * 2},aformat=channel_layouts=stereo,asplit[voz][chave];"
              f"[m][chave]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=500[duck];"
              f"[voz][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[a]")
        run_ffmpeg(["-i", str(base), "-stream_loop", "-1", "-i", str(audio_path), "-filter_complex", fc,
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-t", f"{T:.3f}", "-movflags", "+faststart", str(out)], "música de fundo")
        return out.name, f"narração + {name} de fundo", round(T, 1)

    # manter: a imagem fica como está, o áudio é trocado
    base = next((p for p in (seq_dir / SILENT_MASTER, seq_dir / NARRATED_MASTER, seq_dir / "video.mp4") if p.exists()), None)
    if base is None:
        raise RuntimeError("Gere o vídeo primeiro (com narração ou sem áudio).")
    T = _probe(base)["duration"]
    tmp_out = seq_dir / "video_tmp.mp4"
    progress(0.3, "Unindo o áudio ao vídeo...")
    fc = (f"[1:a]aresample={SR * 2},aformat=channel_layouts=stereo,volume={vol:.2f},{USER_AUDIO_LOUDNESS},"
          f"apad,atrim=0:{T:.3f},afade=t=out:st={max(0, T - 1.2):.2f}:d=1.2[a]")
    run_ffmpeg(["-i", str(base), "-i", str(audio_path), "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{T:.3f}", "-movflags", "+faststart", str(tmp_out)],
               "unir áudio")
    tmp_out.replace(out)
    cut = " — áudio cortado no fim do vídeo" if A > T + 0.5 else " — completado com silêncio" if A < T - 0.5 else ""
    return out.name, f"arquivo: {name}{cut}", round(T, 1)


def _probe(path):
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type", "-of", "json", str(path)], capture_output=True, text=True)
    data = json.loads(r.stdout or "{}")
    return {"duration": float(data.get("format", {}).get("duration") or 0),
            "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", []))}
