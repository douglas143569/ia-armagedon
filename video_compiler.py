"""
ARMAGEDON — Montagem de vídeos (vários vídeos → um vídeo final)

Pipeline:
  1. Biblioteca: vídeos das sequências narradas, do gerador de vídeo, editados e enviados pelo usuário.
  2. Padronização ("mezanino"): cada vídeo vira o mesmo formato — resolução de saída com fundo
     desfocado, 30 fps, H.264, áudio AAC 48 kHz estéreo com volume nivelado (−16 LUFS).
     O resultado fica em cache: remontar ou reordenar não reprocessa o que já foi feito.
  3. Junção: corte seco (sem recodificar) ou transição (xfade + acrossfade, mantendo o sincronismo).
  4. Acabamento: abertura/encerramento, música de fundo com "ducking" (abaixa sob a fala),
     capítulos dentro do MP4 + lista de tempos (para descrição do YouTube) e capa.

Cada montagem é um projeto salvo (projeto.json) em images_generated/montagens/<id>/.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import sequences

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "images_generated"
MONTAGE_DIR = OUTPUT_DIR / "montagens"
CACHE_DIR = MONTAGE_DIR / "_cache"
THUMB_DIR = MONTAGE_DIR / "_thumbs"
MUSIC_DIR = MONTAGE_DIR / "_musicas"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
TRASH_DIR = MONTAGE_DIR / "_lixeira"
TRASH_DAYS = 30   # itens na lixeira há mais tempo que isso são apagados de vez

# fontes de vídeo da biblioteca: tipo → pasta (só arquivos dessas pastas podem ser usados)
SOURCES = {
    "gen": BASE_DIR / "videos_generated",
    "edit": BASE_DIR / "videos_edited",
    "up": UPLOAD_DIR,
}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

FORMATS = {
    "vertical": {"name": "Vertical 9:16 (Reels, TikTok, Shorts)", "size": (1080, 1920)},
    "quadrado": {"name": "Quadrado 1:1 (Instagram, WhatsApp)", "size": (1080, 1080)},
    "horizontal": {"name": "Horizontal 16:9 (YouTube)", "size": (1920, 1080)},
}
TRANSITIONS = {
    "corte": {"name": "Corte seco", "xfade": None},
    "fade": {"name": "Fade (dissolver)", "xfade": "fade"},
    "preto": {"name": "Fade pelo preto", "xfade": "fadeblack"},
    "deslizar": {"name": "Deslizar", "xfade": "slideleft"},
    "zoom": {"name": "Zoom", "xfade": "zoomin"},
}
FPS = 30
AR = 48000
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"
MEZZANINE_VERSION = "v1"   # mude se a receita da padronização mudar (invalida o cache)

for d in (MONTAGE_DIR, CACHE_DIR, THUMB_DIR, MUSIC_DIR, UPLOAD_DIR, TRASH_DIR):
    d.mkdir(parents=True, exist_ok=True)


class Cancelled(Exception):
    pass

# ============================ FFMPEG ============================


def tool(name):
    exe = shutil.which(name)
    if not exe:
        raise RuntimeError(f"{name} não encontrado. Instale com: winget install Gyan.FFmpeg")
    return exe


def run_ffmpeg(args, what, total=None, progress=None, cancelled=None):
    """Roda o ffmpeg; se total (s) e progress forem dados, informa a fração concluída."""
    cmd = [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostats", "-y"]
    if progress and total:
        cmd += ["-progress", "pipe:1"]
    proc = subprocess.Popen(cmd + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    if progress and total:
        for line in proc.stdout:
            if cancelled and cancelled():
                proc.kill()
                raise Cancelled()
            m = re.match(r"out_time_us=(\d+)", line)
            if m:
                progress(min(1.0, int(m.group(1)) / 1e6 / total))
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ({what}): {err.strip()[-500:]}")


_probe_cache = {}


def probe(path):
    """Duração, tamanho e se tem áudio (com cache por data de modificação)."""
    path = Path(path)
    key = (str(path), path.stat().st_mtime)
    if key in _probe_cache:
        return _probe_cache[key]
    r = subprocess.run([tool("ffprobe"), "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
                       capture_output=True, text=True)
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    info = {
        "duration": float(data.get("format", {}).get("duration") or 0),
        "width": video.get("width"), "height": video.get("height"),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }
    _probe_cache[key] = info
    return info


def fmt_time(seconds):
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

# ============================ BIBLIOTECA ============================


def _thumb(path):
    """Miniatura (jpg) de um vídeo, gerada uma vez e guardada."""
    path = Path(path)
    key = hashlib.sha1(f"{path}|{path.stat().st_mtime}".encode()).hexdigest()[:16]
    out = THUMB_DIR / f"{key}.jpg"
    if not out.exists():
        dur = probe(path)["duration"]
        try:
            run_ffmpeg(["-ss", f"{min(1.0, dur / 3):.2f}", "-i", str(path), "-frames:v", "1",
                        "-vf", "scale=360:-2", "-q:v", "4", str(out)], "miniatura")
        except RuntimeError:
            return None
    return f"montagens/_thumbs/{out.name}"


def library():
    """Todos os vídeos disponíveis para montar, mais recentes primeiro."""
    items = []
    for d in sorted((OUTPUT_DIR / "sequences").glob("seq_*")):
        video = d / "video.mp4"
        if not video.exists():
            continue
        try:
            ctx = json.loads((d / "sequencia.json").read_text(encoding="utf-8"))
        except Exception:
            ctx = {}
        kind = sequences.TYPES.get(ctx.get("type"), {}).get("name", "Sequência")
        thumb = d / "quadro_01.png"
        items.append({
            "id": f"seq:{d.name}", "source": "Sequência narrada", "kind": kind,
            "title": ctx.get("plan", {}).get("title") or d.name,
            "duration": round(probe(video)["duration"], 1), "mtime": video.stat().st_mtime,
            "video": f"sequences/{d.name}/video.mp4",
            "thumb": f"sequences/{d.name}/{thumb.name}" if thumb.exists() else _thumb(video),
        })
    labels = {"gen": "Gerador de vídeo", "edit": "Vídeo editado", "up": "Enviado do computador"}
    for src, folder in SOURCES.items():
        if not folder.exists():
            continue
        for f in folder.iterdir():
            if f.suffix.lower() not in VIDEO_EXT or not f.is_file():
                continue
            try:
                info = probe(f)
            except Exception:
                continue
            if info["duration"] <= 0:
                continue
            items.append({
                "id": f"{src}:{f.name}", "source": labels[src], "kind": "GIF" if f.suffix.lower() == ".gif" else "Vídeo",
                "title": f.stem, "duration": round(info["duration"], 1), "mtime": f.stat().st_mtime,
                "video": None if f.suffix.lower() == ".gif" else f"file/{src}/{f.name}",
                "thumb": _thumb(f),
            })
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return items


def resolve(item_id):
    """id da biblioteca → (caminho do arquivo, título). Só aceita arquivos das pastas conhecidas."""
    kind, _, name = str(item_id).partition(":")
    name = Path(name).name
    if kind == "seq":
        path = OUTPUT_DIR / "sequences" / name / "video.mp4"
        try:
            ctx = json.loads((path.parent / "sequencia.json").read_text(encoding="utf-8"))
            title = ctx.get("plan", {}).get("title") or name
        except Exception:
            title = name
    elif kind in SOURCES:
        path, title = SOURCES[kind] / name, Path(name).stem
    else:
        raise ValueError(f"Vídeo desconhecido: {item_id}")
    if not path.is_file():
        raise ValueError(f"Arquivo não encontrado: {item_id}")
    return path, title


def file_path(kind, name):
    """Arquivo de uma pasta da biblioteca (para tocar no navegador)."""
    if kind not in SOURCES:
        return None
    path = SOURCES[kind] / Path(name).name
    return path if path.is_file() else None


def save_upload(storage, folder, allowed):
    """Grava um arquivo enviado (vídeo ou música) com nome seguro e único."""
    name = Path(storage.filename or "arquivo").name
    ext = Path(name).suffix.lower()
    if ext not in allowed:
        raise ValueError(f"Formato não suportado ({ext or 'sem extensão'}).")
    stem = re.sub(r"[^\w\-]+", "_", Path(name).stem, flags=re.UNICODE).strip("_")[:60] or "arquivo"
    out = folder / f"{stem}{ext}"
    n = 2
    while out.exists():
        out = folder / f"{stem}_{n}{ext}"
        n += 1
    storage.save(out)
    return out

# ============================ PADRONIZAÇÃO ============================


def mezzanine(src, size, trim_start=0.0, trim_end=None, progress=None, cancelled=None):
    """Converte um vídeo para o formato padrão da montagem (com cache). Retorna (caminho, duração)."""
    src = Path(src)
    W, H = size
    info = probe(src)
    start = max(0.0, float(trim_start or 0))
    end = min(info["duration"], float(trim_end)) if trim_end else info["duration"]
    if end - start < 0.3:
        raise ValueError(f"Trecho muito curto depois do corte: {src.name}")
    key = hashlib.sha1(f"{src}|{src.stat().st_mtime}|{src.stat().st_size}|{W}x{H}|{start:.2f}|{end:.2f}|"
                       f"{MEZZANINE_VERSION}".encode()).hexdigest()[:20]
    out = CACHE_DIR / f"{key}.mp4"
    duration = end - start
    if out.exists():
        return out, probe(out)["duration"]

    # vídeo: preenche o quadro com uma cópia desfocada e põe o vídeo inteiro por cima, centralizado
    vf = (f"[0:v]fps={FPS},split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,eq=brightness=-0.12[bg];"
          f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]")
    args = ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src)]
    if info["has_audio"]:
        af = f"[0:a]aresample={AR},aformat=channel_layouts=stereo,{LOUDNESS}[aout]"
    else:  # vídeo mudo: cria uma trilha de silêncio para todos os trechos terem áudio
        args += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", f"anullsrc=r={AR}:cl=stereo"]
        af = f"[1:a]aresample={AR},aformat=channel_layouts=stereo[aout]"
    tmp = out.with_suffix(".tmp.mp4")
    run_ffmpeg(args + ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[aout]",
                       "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
                       "-g", str(FPS * 2), "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "192k", "-ar", str(AR), "-ac", "2",
                       "-t", f"{duration:.3f}", str(tmp)],
               f"padronizar {src.name}", duration, progress, cancelled)
    tmp.replace(out)
    return out, probe(out)["duration"]


def title_card(title, subtitle, size, seconds, out, cancelled=None):
    """Abertura/encerramento: cartão com título, subtítulo e marca, com leve zoom e fade."""
    W, H = size
    img = Image.new("RGB", size, (9, 5, 8))
    d = ImageDraw.Draw(img)
    for y in range(H):  # degradê vertical escuro → vinho
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(9 + 40 * t), int(5 + 8 * t), int(8 + 10 * t)))
    # brilho vermelho atrás do título, bem desfocado (sem borda visível)
    glow = Image.new("L", size, 0)
    rx, ry = int(min(W, H) * 0.42), int(min(W, H) * 0.24)
    ImageDraw.Draw(glow).ellipse([W / 2 - rx, H * 0.46 - ry, W / 2 + rx, H * 0.46 + ry], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(min(W, H) * 0.12))
    img = Image.composite(Image.new("RGB", size, (88, 14, 22)), img, glow.point(lambda v: int(v * 0.55)))
    d = ImageDraw.Draw(img)
    base = min(W, H)
    ft = sequences.font(["segoeuib.ttf", "arialbd.ttf"], int(base * 0.085))
    fs = sequences.font(["segoeui.ttf", "arial.ttf"], int(base * 0.04))
    fb = sequences.font(["segoeuib.ttf", "arialbd.ttf"], int(base * 0.028))
    lines = sequences.wrap(d, title or "", ft, int(W * 0.84))
    lh = int(ft.size * 1.15)
    sub_lines = sequences.wrap(d, subtitle or "", fs, int(W * 0.8)) if subtitle else []
    block = lh * len(lines) + (int(base * 0.05) + int(fs.size * 1.3) * len(sub_lines) if sub_lines else 0)
    y = int(H * 0.46 - block / 2)
    for ln in lines:
        d.text(((W - d.textlength(ln, font=ft)) / 2, y), ln, font=ft, fill=(255, 255, 255))
        y += lh
    if sub_lines:
        y += int(base * 0.02)
        bar = int(base * 0.08)
        d.rectangle([(W - bar) / 2, y, (W + bar) / 2, y + max(4, base // 200)], fill=sequences.ACCENT)
        y += int(base * 0.03)
        for ln in sub_lines:
            d.text(((W - d.textlength(ln, font=fs)) / 2, y), ln, font=fs, fill=(225, 205, 200))
            y += int(fs.size * 1.3)
    brand = "ARMAGEDON"
    d.text(((W - d.textlength(brand, font=fb)) / 2, H - int(base * 0.09)), brand, font=fb, fill=(255, 111, 60))
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "card.png"
        img.resize((W * 2, H * 2), Image.LANCZOS).save(png)
        frames = int(seconds * FPS)
        vf = (f"[0:v]zoompan=z='1+0.04*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
              f"fade=t=in:st=0:d=0.5,fade=t=out:st={seconds - 0.5:.2f}:d=0.5,setsar=1,format=yuv420p[v]")
        run_ffmpeg(["-i", str(png), "-f", "lavfi", "-t", f"{seconds:.2f}", "-i", f"anullsrc=r={AR}:cl=stereo",
                    "-filter_complex", vf, "-map", "[v]", "-map", "1:a", "-frames:v", str(frames), "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high", "-g", str(FPS * 2),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(AR), "-ac", "2",
                    "-t", f"{seconds:.2f}", str(out)], "cartão de título", cancelled=cancelled)
    return out, seconds

# ============================ MONTAGEM ============================


def validate_project(p):
    """Normaliza e valida o pedido de montagem. Retorna o projeto limpo."""
    items = []
    for it in p.get("items") or []:
        path, title = resolve(it.get("id"))
        ts = float(it.get("trim_start") or 0)
        te = float(it["trim_end"]) if it.get("trim_end") not in (None, "", 0, "0") else None
        if te is not None and te <= ts:
            raise ValueError(f"Corte inválido em “{title}”: o fim precisa ser depois do início.")
        items.append({"id": it["id"], "title": str(it.get("title") or title).strip()[:120] or title,
                      "trim_start": ts, "trim_end": te})
    if not items:
        raise ValueError("Escolha pelo menos um vídeo para a montagem.")
    fmt = p.get("format") if p.get("format") in FORMATS else "auto"
    transition = p.get("transition") if p.get("transition") in TRANSITIONS else "fade"
    music = p.get("music") or {}
    if music.get("file") and not (MUSIC_DIR / Path(music["file"]).name).is_file():
        raise ValueError("Música de fundo não encontrada; envie de novo.")
    return {
        "title": str(p.get("title") or "Minha montagem").strip()[:120],
        "items": items, "format": fmt, "transition": transition,
        "transition_duration": max(0.2, min(2.0, float(p.get("transition_duration") or 0.7))),
        "intro": {"enabled": bool((p.get("intro") or {}).get("enabled")),
                  "title": str((p.get("intro") or {}).get("title") or p.get("title") or "").strip()[:120],
                  "subtitle": str((p.get("intro") or {}).get("subtitle") or "").strip()[:160]},
        "outro": {"enabled": bool((p.get("outro") or {}).get("enabled")),
                  "title": str((p.get("outro") or {}).get("title") or "Obrigado por assistir!").strip()[:120],
                  "subtitle": str((p.get("outro") or {}).get("subtitle") or "").strip()[:160]},
        "music": {"file": Path(music["file"]).name if music.get("file") else None,
                  "volume": max(0.02, min(1.0, float(music.get("volume") or 0.25)))},
        "chapters": bool(p.get("chapters", True)),
    }


def auto_format(first_path):
    info = probe(first_path)
    w, h = info.get("width") or 1080, info.get("height") or 1080
    if h > w * 1.15:
        return "vertical"
    if w > h * 1.15:
        return "horizontal"
    return "quadrado"


def compile_project(project, progress=lambda f, m: None, cancelled=lambda: False, montage_id=None):
    """Renderiza a montagem. Retorna o dict de resultado (arquivos, duração, capítulos)."""
    t0 = time.time()
    montage_id = montage_id or f"mont_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = MONTAGE_DIR / montage_id
    out_dir.mkdir(parents=True, exist_ok=True)
    first_path, _ = resolve(project["items"][0]["id"])
    fmt = project["format"] if project["format"] in FORMATS else auto_format(first_path)
    size = FORMATS[fmt]["size"]
    (out_dir / "projeto.json").write_text(json.dumps({**project, "format_resolved": fmt}, ensure_ascii=False, indent=2),
                                          encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        segments = []   # (arquivo, duração, título do capítulo)

        # 1) abertura
        if project["intro"]["enabled"] and project["intro"]["title"]:
            progress(0.01, "Criando a abertura...")
            segments.append((*title_card(project["intro"]["title"], project["intro"]["subtitle"], size, 4.0,
                                         tmp / "intro.mp4", cancelled), "Abertura"))

        # 2) padroniza cada vídeo (com cache), com progresso proporcional à duração
        sources = []
        for it in project["items"]:
            path, _ = resolve(it["id"])
            info = probe(path)
            end = min(info["duration"], it["trim_end"]) if it["trim_end"] else info["duration"]
            sources.append((path, it, max(0.3, end - it["trim_start"])))
        total_src = sum(d for _, _, d in sources) or 1
        done = 0.0
        for k, (path, it, dur) in enumerate(sources):
            if cancelled():
                raise Cancelled()
            label = f"Padronizando {k + 1}/{len(sources)}: {it['title'][:40]}"

            def sub(frac, done=done, dur=dur, label=label):
                progress(0.03 + 0.67 * (done + frac * dur) / total_src, label)

            sub(0)
            seg, seg_dur = mezzanine(path, size, it["trim_start"], it["trim_end"], sub, cancelled)
            segments.append((seg, seg_dur, it["title"]))
            done += dur

        # 3) encerramento
        if project["outro"]["enabled"] and project["outro"]["title"]:
            progress(0.71, "Criando o encerramento...")
            segments.append((*title_card(project["outro"]["title"], project["outro"]["subtitle"], size, 3.5,
                                         tmp / "outro.mp4", cancelled), "Encerramento"))

        # 4) junta os trechos
        xf = TRANSITIONS[project["transition"]]["xfade"]
        X = project["transition_duration"] if xf and len(segments) > 1 else 0.0
        X = min(X, min(d for _, d, _ in segments) / 2)   # a transição não pode ser maior que metade do trecho mais curto
        starts, t = [], 0.0
        for i, (_, d, _) in enumerate(segments):
            starts.append(t)
            t += d - (X if i < len(segments) - 1 else 0)
        total = t
        joined = tmp / "junto.mp4"
        progress(0.72, "Juntando os vídeos...")
        if not xf or len(segments) == 1:
            listfile = tmp / "lista.txt"
            listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p, _, _ in segments), encoding="utf-8")
            run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(joined)],
                       "juntar (corte seco)", total, lambda f: progress(0.72 + 0.2 * f, "Juntando os vídeos..."), cancelled)
        else:
            args, vchain, achain = [], [], []
            for p, _, _ in segments:
                args += ["-i", str(p)]
            pv, pa, acc = "[0:v]", "[0:a]", 0.0
            for i in range(1, len(segments)):
                acc += segments[i - 1][1] - X
                ov, oa = (f"[v{i}]", f"[a{i}]") if i < len(segments) - 1 else ("[v]", "[a]")
                vchain.append(f"{pv}[{i}:v]xfade=transition={xf}:duration={X:.3f}:offset={acc:.3f}{ov}")
                achain.append(f"{pa}[{i}:a]acrossfade=d={X:.3f}:c1=tri:c2=tri{oa}")
                pv, pa = ov, oa
            run_ffmpeg(args + ["-filter_complex", ";".join(vchain + achain), "-map", "[v]", "-map", "[a]",
                               "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
                               "-g", str(FPS * 2), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(AR),
                               str(joined)],
                       "juntar com transições", total, lambda f: progress(0.72 + 0.2 * f, "Juntando os vídeos..."), cancelled)

        # 5) música de fundo com ducking: abaixa sozinha quando há fala
        mixed = joined
        if project["music"]["file"]:
            progress(0.93, "Mixando a música de fundo...")
            music = MUSIC_DIR / project["music"]["file"]
            mixed = tmp / "com_musica.mp4"
            vol = project["music"]["volume"]
            fc = (f"[1:a]aresample={AR},aformat=channel_layouts=stereo,volume={vol:.3f},"
                  f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5[m];"
                  f"[0:a]asplit[voz][chave];"
                  f"[m][chave]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=500[duck];"
                  f"[voz][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[a]")
            run_ffmpeg(["-i", str(joined), "-stream_loop", "-1", "-i", str(music), "-filter_complex", fc,
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(AR),
                        "-t", f"{total:.3f}", str(mixed)], "música de fundo", total,
                       lambda f: progress(0.93 + 0.04 * f, "Mixando a música de fundo..."), cancelled)

        # 6) capítulos + arquivo final (faststart: começa a tocar antes de baixar tudo)
        progress(0.97, "Finalizando...")
        chapters = [{"start": round(s, 2), "title": title} for s, (_, _, title) in zip(starts, segments)]
        meta = tmp / "meta.txt"
        lines = [";FFMETADATA1", f"title={project['title']}", "comment=Feito com ARMAGEDON"]
        if project["chapters"]:
            for i, c in enumerate(chapters):
                end = chapters[i + 1]["start"] if i + 1 < len(chapters) else total
                safe = re.sub(r"([=;#\\\n])", r"\\\1", c["title"])
                lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(c['start'] * 1000)}", f"END={int(end * 1000)}",
                          f"title={safe}"]
        meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
        final = out_dir / "video_final.mp4"
        run_ffmpeg(["-i", str(mixed), "-i", str(meta), "-map", "0", "-map_metadata", "1", "-map_chapters", "1",
                    "-c", "copy", "-movflags", "+faststart", str(final)], "finalizar")

    run_ffmpeg(["-ss", f"{min(total / 2, chapters[1]['start'] + 1 if len(chapters) > 1 else 1):.2f}", "-i", str(final),
                "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(out_dir / "capa.jpg")], "capa")
    chapter_text = "\n".join(f"{fmt_time(c['start'])} {c['title']}" for c in chapters)
    (out_dir / "capitulos.txt").write_text(chapter_text + "\n", encoding="utf-8")
    result = {
        "id": montage_id, "title": project["title"], "format": fmt, "format_name": FORMATS[fmt]["name"],
        "size": f"{size[0]}x{size[1]}", "duration": round(total, 1), "duration_text": fmt_time(total),
        "chapters": chapters, "chapters_text": chapter_text, "segments": len(segments),
        "video": f"montagens/{montage_id}/video_final.mp4", "cover": f"montagens/{montage_id}/capa.jpg",
        "render_seconds": round(time.time() - t0), "bytes": final.stat().st_size,
    }
    (out_dir / "resultado.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(1.0, "Montagem pronta")
    return result


# ============================ LIXEIRA ============================
# Excluir não apaga na hora: o item vai para _lixeira/<id>/ com um manifesto (de onde veio, título, miniatura),
# pode ser restaurado, e é apagado de vez só pelo usuário ou depois de TRASH_DAYS dias.


def _locate(item_id):
    """id → (caminho do arquivo/pasta, título, miniatura relativa). Só dentro das pastas conhecidas."""
    kind, _, name = str(item_id).partition(":")
    name = Path(name).name
    if not name:
        raise ValueError("Item inválido.")
    if kind == "seq":
        path = OUTPUT_DIR / "sequences" / name
        title = name
        try:
            title = json.loads((path / "sequencia.json").read_text(encoding="utf-8")).get("plan", {}).get("title") or name
        except Exception:
            pass
        thumb = "quadro_01.png"
    elif kind == "mont":
        path = MONTAGE_DIR / name
        title = name
        try:
            title = json.loads((path / "resultado.json").read_text(encoding="utf-8")).get("title") or name
        except Exception:
            pass
        thumb = "capa.jpg"
    elif kind in SOURCES:
        path, title, thumb = SOURCES[kind] / name, Path(name).stem, None
    else:
        raise ValueError(f"Item desconhecido: {item_id}")
    if not path.exists():
        raise ValueError(f"“{title}” não existe mais.")
    return path, title, thumb


def trash(item_ids):
    """Move os itens para a lixeira. Retorna os ids da lixeira (para o "Desfazer")."""
    moved = []
    for item_id in item_ids:
        path, title, thumb = _locate(item_id)
        tid = f"{time.strftime('%Y%m%d_%H%M%S')}_{hashlib.sha1(str(item_id).encode()).hexdigest()[:8]}"
        slot = TRASH_DIR / tid
        slot.mkdir(parents=True)
        thumb_rel = None
        if thumb is None and path.is_file():   # vídeo solto: guarda a miniatura junto, para mostrar na lixeira
            src = _thumb(path)
            if src:
                shutil.copy2(OUTPUT_DIR / src, slot / "miniatura.jpg")
                thumb_rel = "miniatura.jpg"
        shutil.move(str(path), str(slot / path.name))
        if thumb:
            thumb_rel = f"{path.name}/{thumb}"
        manifest = {"id": tid, "item_id": item_id, "title": title, "original": str(path),
                    "kind": str(item_id).split(":")[0], "deleted_at": time.time(), "thumb": thumb_rel}
        (TRASH_DIR / f"{tid}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        moved.append(tid)
    return moved


def _purge_one(tid):
    tid = Path(tid).name
    shutil.rmtree(TRASH_DIR / tid, ignore_errors=True)
    (TRASH_DIR / f"{tid}.json").unlink(missing_ok=True)


def list_trash():
    """Itens na lixeira, mais recentes primeiro (e apaga de vez os vencidos)."""
    out = []
    for m in TRASH_DIR.glob("*.json"):
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue
        age_days = (time.time() - data.get("deleted_at", 0)) / 86400
        if age_days > TRASH_DAYS:
            _purge_one(data["id"])
            continue
        data["days_left"] = max(0, int(TRASH_DAYS - age_days))
        data["thumb_rel"] = f"montagens/_lixeira/{data['id']}/{data['thumb']}" if data.get("thumb") else None
        out.append(data)
    out.sort(key=lambda d: d["deleted_at"], reverse=True)
    return out


def restore(tids):
    """Devolve itens da lixeira ao lugar de origem. Retorna quantos voltaram."""
    count = 0
    for tid in tids:
        tid = Path(tid).name
        manifest = TRASH_DIR / f"{tid}.json"
        if not manifest.exists():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        original = Path(data["original"])
        if original.exists():
            raise ValueError(f"Já existe outro “{data['title']}” no lugar original.")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(TRASH_DIR / tid / original.name), str(original))
        _purge_one(tid)
        count += 1
    return count


def purge(tids=None):
    """Apaga de vez (tids=None → esvazia a lixeira). Retorna quantos foram apagados."""
    items = [d["id"] for d in list_trash()] if tids is None else [Path(t).name for t in tids]
    for tid in items:
        _purge_one(tid)
    return len(items)


def compilations():
    """Montagens já feitas, mais recentes primeiro."""
    out = []
    for d in sorted(MONTAGE_DIR.glob("mont_*"), reverse=True):
        try:
            res = json.loads((d / "resultado.json").read_text(encoding="utf-8"))
            res["project"] = json.loads((d / "projeto.json").read_text(encoding="utf-8"))
            out.append(res)
        except Exception:
            continue
    return out
