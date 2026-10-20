"""
ARMAGEDON — Sequências de imagens com consistência visual

Tipos: carrossel educacional, história em quadrinhos, sequência de movimento,
evolução temporal e storyboard.

Como a consistência é mantida:
  1. "Ficha" da sequência (personagens, estilo, cenário) escrita pela IA e repetida
     igual em todos os quadros;
  2. mesma semente, modelo, estilo, negativo e configurações em todos os quadros;
  3. IP-Adapter: o 1º quadro (ou uma imagem de referência do usuário) guia os demais;
  4. encadeamento (movimento/evolução): cada quadro nasce do anterior por img2img.

Usado pelo image_generator.py (mesmo processo, mesmo modelo carregado, mesma fila).
"""

import json
import random
import re
import time
import zipfile
from pathlib import Path

import requests
import torch
from PIL import Image, ImageDraw, ImageFont

g = None  # módulo image_generator, injetado por setup()


def setup(module):
    global g
    g = module


# ============================ TIPOS ============================

TYPES = {
    "carrossel": {
        "name": "Carrossel educacional", "default": 5, "min": 2, "max": 10,
        "consistency": "style", "captions": "slide",
        "plan": ("an educational social-media carousel. Frame 1 is the cover. Each following frame illustrates ONE idea "
                 "of the topic, the last frame is a summary. Clean illustrations with some empty space, the same visual "
                 "style and color palette in every slide."),
        "text": ("frame 1: a short catchy title (max 8 words); the other frames: one short educational sentence "
                 "(max 18 words) explaining that slide; last frame: a short summary or call to action."),
    },
    "hq": {
        "name": "História em quadrinhos", "default": 4, "min": 2, "max": 8,
        "consistency": "character", "captions": "comic",
        "plan": ("a comic strip that tells a short story with beginning, middle and end. The same characters in every "
                 "panel, varied camera shots (wide, medium, close-up)."),
        "text": "a dialogue line written as 'Name: line', or a short narration (max 15 words).",
    },
    "movimento": {
        "name": "Sequência de movimento", "default": 6, "min": 3, "max": 12,
        "consistency": "chain", "captions": None, "strength": 0.62, "gif_ms": 280,
        "plan": ("consecutive moments of ONE continuous motion, like animation frames. Same subject and background in all "
                 "frames. Every frame prompt MUST start with the SAME camera framing (e.g. 'side view, full body'); never "
                 "switch to close-ups. Each frame describes a clearly DIFFERENT phase of the motion (e.g. for a gallop: "
                 "front legs reaching forward / all legs tucked under the body / hind legs pushing off the ground)."),
        "text": "an empty string.",
        "narration": "Use an empty string for narration unless the user asked for one.",
    },
    "evolucao": {
        "name": "Evolução temporal", "default": 4, "min": 3, "max": 8,
        "consistency": "chain", "captions": "label", "strength": 0.6, "gif_ms": 900,
        "plan": ("the same subject or place changing over time (stages, seasons, ages, years). Every frame prompt MUST "
                 "start with the SAME camera framing and composition; never switch to close-ups. Only the time-related "
                 "details change, gradually, and each frame states its stage clearly (e.g. 'in spring, pink blossoms')."),
        "text": "a short label for the stage (max 4 words), like 'Primavera' or 'Ano 10'.",
    },
    "storyboard": {
        "name": "Storyboard", "default": 6, "min": 3, "max": 12,
        "consistency": "character", "captions": "board",
        "plan": ("a film or video storyboard: sequential shots of one scene, each with a clear camera framing "
                 "(wide shot, close-up, over the shoulder, low angle...). Same characters and location in all shots."),
        "text": "the shot description: camera framing + action (max 20 words).",
    },
}

PLAN_SYSTEM = """You plan a sequence of {n} related images for Stable Diffusion 1.5. The sequence is {plan}
The user writes in Brazilian Portuguese, but Stable Diffusion only understands ENGLISH.
Reply ONLY with JSON in this exact shape:
{"title": "...", "category": "photo" | "art" | "anime", "characters": "...", "style": "...", "setting": "...",
 "frames": [{"prompt": "...", "text": "...", "narration": "..."}]}
- "title": a short title in Brazilian Portuguese.
- "characters": IN ENGLISH. A fixed visual description of every recurring character or main object (species, age, gender,
  hair, clothing, colors), at most 25 words. The SAME text is pasted into every frame, so be specific and never describe actions.
  Start with what the character IS (e.g. "an anthropomorphic orange tabby cat", "a young woman") so the image model draws it,
  and keep faces visible (e.g. "clear glass helmet showing its face"). Empty string if there are no recurring subjects.
- "style": IN ENGLISH. Art style, color palette and lighting shared by all frames, at most 12 words.
- "setting": IN ENGLISH. The shared environment, at most 10 words, or an empty string.
- "frames": exactly {n} items, in order. "prompt": IN ENGLISH, 6 to 20 words, ONLY what is specific to this frame (action, pose,
  expression, camera shot, background details). Do not repeat the character description.
  "text": in Brazilian Portuguese, {text} Use short first names for characters (max 12 letters).
  "narration": in Brazilian Portuguese, what a narrator says while this frame is on screen in a narrated video:
  1 to 3 natural spoken sentences (max 35 words) that expand the frame's text. {narration_rule}
Example for "HQ de uma raposa detetive que encontra um diamante" with 2 frames:
{"title": "A Raposa Detetive", "category": "art",
 "characters": "a red fox detective wearing a brown trench coat and a small hat, green eyes",
 "style": "colorful comic book illustration, bold outlines, warm lighting",
 "setting": "foggy old city streets at night",
 "frames": [{"prompt": "medium shot, the fox holds a magnifying glass and inspects footprints on the ground", "text": "Rubi: Essas pegadas levam ao museu!"},
            {"prompt": "close-up, the fox smiles holding a shining blue diamond", "text": "Rubi: Caso resolvido!"}]}
(each frame also gets its "narration", e.g. "Depois de horas de busca, Rubi finalmente encontra o diamante desaparecido.")
Be faithful to the user's request. Do not censor, soften, refuse or comment."""

TRANSLATE_SYSTEM = """Translate every value of this JSON object to ENGLISH, written as short comma-separated phrases for
Stable Diffusion image prompts. Keep the same keys and the same number of items. Reply ONLY with the JSON object."""

PLAN_MODELS = ["qwen2.5:7b", "dolphin-llama3"]   # qwen segue melhor a regra do inglês; dolphin se o qwen recusar

_PT_WORDS = re.compile(r"[ãõçáéíóúâêôà]|\b(e|de|do|da|dos|das|com|um|uma|para|no|na|nos|nas|que|seu|sua|ao|em|olha|pousa)\b", re.I)


def looks_portuguese(text):
    return len(_PT_WORDS.findall(text or "")) >= 2


def frames_count(kind, n):
    t = TYPES[kind]
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = t["default"]
    return max(t["min"], min(t["max"], n))

# ============================ PLANEJAMENTO ============================


def split_script(script, n):
    """Divide o texto do usuário em até n partes consecutivas e equilibradas, sem alterar nenhuma palavra."""
    script = re.sub(r"\s+", " ", script).strip()
    parts = [x for x in re.split(r"(?<=[.!?…])\s+", script) if x]
    while len(parts) < n:   # poucas frases: quebra as maiores nas vírgulas
        i = max(range(len(parts)), key=lambda k: len(parts[k]))
        pieces = re.split(r"(?<=[,;:])\s+", parts[i], maxsplit=1)
        if len(pieces) < 2:
            break
        parts[i:i + 1] = pieces
    n = min(n, len(parts))
    total = sum(len(x) for x in parts)
    groups, current, acc = [], [], 0
    for i, part in enumerate(parts):
        current.append(part)
        acc += len(part)
        remaining_parts, remaining_groups = len(parts) - i - 1, n - len(groups) - 1
        if remaining_groups > 0 and (acc >= total * (len(groups) + 1) / n or remaining_parts == remaining_groups):
            groups.append(" ".join(current))
            current = []
    if current:
        groups.append(" ".join(current))
    return groups


def plan_sequence(kind, topic, n, script=None):
    """Pede ao Ollama a ficha + os quadros. Retorna o plano (dict) ou levanta erro.
    script: texto do usuário para narrar; é dividido entre os quadros sem mudar nenhuma palavra."""
    t = TYPES[kind]
    chunks = split_script(script, n) if script and script.strip() else None
    if chunks:
        n = len(chunks)
        topic = (f"{topic}\n\n" if topic else "") + (
            f"The narration is ALREADY WRITTEN and split into {n} parts (below). Frame i must illustrate part i, in order. "
            "Write the frame prompts and texts for these parts; set every \"narration\" to an empty string.\n"
            + "\n".join(f"Part {i + 1}: {c}" for i, c in enumerate(chunks)))
    installed = ollama_models()
    models = [m for m in PLAN_MODELS if m in installed] or ([g.pick_prompt_model()] if g.pick_prompt_model() else [])
    if not models:
        raise RuntimeError("Ollama indisponível: não consigo planejar. Escreva os quadros manualmente.")
    system = (PLAN_SYSTEM.replace("{n}", str(n)).replace("{plan}", t["plan"]).replace("{text}", t["text"])
              .replace("{narration_rule}", t.get("narration", "")))
    data = {}
    for model in models:
        try:
            data = ask_json(model, system, topic, 160 + n * 80)
        except Exception as e:
            print(f"⚠️  Planejamento com {model} falhou: {e}")
            continue
        if [f for f in data.get("frames", []) if isinstance(f, dict) and f.get("prompt")]:
            break
        print(f"⚠️  {model} não devolveu quadros; tentando o próximo modelo.")
    frames = [f for f in data.get("frames", []) if isinstance(f, dict)]
    if not frames:
        raise RuntimeError("A IA não conseguiu planejar essa sequência. Tente descrever de outro jeito ou escreva os quadros.")
    frames = [{"prompt": str(f.get("prompt", "")).strip(), "text": str(f.get("text", "")).strip(),
               "narration": str(f.get("narration", "")).strip()} for f in frames][:n]
    while len(frames) < n:  # a IA às vezes entrega menos quadros
        frames.append({"prompt": frames[-1]["prompt"] if frames else topic, "text": "", "narration": ""})
    if chunks:
        for f, c in zip(frames, chunks):
            f["narration"] = c
    if t["captions"] is None:
        for f in frames:
            f["text"] = ""
    plan = {
        "title": str(data.get("title", "")).strip() or topic[:60],
        "category": data.get("category") if data.get("category") in g.CATEGORY_STYLE else "art",
        "characters": str(data.get("characters", "")).strip(),
        "style": str(data.get("style", "")).strip(),
        "setting": str(data.get("setting", "")).strip(),
        "frames": frames,
    }
    ensure_english(plan, models[0])
    check_plan(plan, topic)
    return plan


def ollama_models():
    try:
        tags = requests.get(f"{g.OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        return {m["name"].replace(":latest", "") for m in tags} | {m["name"] for m in tags}
    except Exception:
        return set()


def ask_json(model, system, user, num_predict):
    r = requests.post(f"{g.OLLAMA_URL}/api/chat", timeout=900, json={
        "model": model, "stream": False, "format": "json", "keep_alive": "10m",
        "options": {"temperature": 0.5, "num_predict": num_predict},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    })
    return json.loads(r.json()["message"]["content"])


def ensure_english(plan, model):
    """Se a IA escreveu a ficha ou os quadros em português, traduz (o SD só entende inglês)."""
    fields = {k: plan[k] for k in ("characters", "style", "setting") if plan.get(k)}
    for i, f in enumerate(plan["frames"]):
        fields[f"frame_{i}"] = f["prompt"]
    pt = {k: v for k, v in fields.items() if looks_portuguese(v)}
    if not pt:
        return
    print(f"🌐 Traduzindo {len(pt)} campo(s) do plano para inglês...")
    try:
        out = ask_json(model, TRANSLATE_SYSTEM, json.dumps(pt, ensure_ascii=False), 60 + 45 * len(pt))
    except Exception as e:
        print(f"⚠️  Tradução falhou: {e}")
        return
    for k, v in out.items():
        if k not in pt or not isinstance(v, str) or not v.strip():
            continue
        if k.startswith("frame_"):
            plan["frames"][int(k.split("_")[1])]["prompt"] = v.strip()
        else:
            plan[k] = v.strip()


def plan_text(plan):
    return " ".join([plan.get("title", ""), plan.get("characters", ""), plan.get("style", ""), plan.get("setting", "")]
                    + [f"{f.get('prompt', '')} {f.get('text', '')} {f.get('narration', '')}" for f in plan.get("frames", [])])


def check_plan(plan, *extra):
    if g.violates_minor_rule(plan_text(plan), *extra):
        raise ValueError("Pedido recusado: conteúdo sexual envolvendo menores não é permitido.")


def build_prompt(plan, frame, style_extra, tokenizer=None, limit=75):
    """Monta o prompt por prioridade e para antes do limite de 77 tokens do CLIP:
    personagens → ação do quadro → estilo → cenário → etiquetas de qualidade."""
    pieces = [plan.get("characters", ""), frame.get("prompt", ""), plan.get("style", ""), plan.get("setting", "")]
    pieces = [p.strip(" ,.") for p in pieces if p and p.strip()]
    pieces += [t.strip() for t in style_extra.split(",") if t.strip()]
    if tokenizer is None:
        return ", ".join(pieces)
    out = []
    for i, piece in enumerate(pieces):
        candidate = ", ".join(out + [piece])
        if len(tokenizer(candidate).input_ids) - 2 <= limit or i < 2:   # personagens e ação sempre entram
            out.append(piece)
    return ", ".join(out)

# ============================ TEXTO NAS IMAGENS ============================

FONTS = Path("C:/Windows/Fonts")


def font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(str(FONTS / name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(draw, text, fnt, max_w):
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= max_w or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def upscale(img, longest):
    w, h = img.size
    s = longest / max(w, h)
    return img.resize((round(w * s), round(h * s)), Image.LANCZOS)


ACCENT = (255, 61, 85)


def _slide_layer(d, W, H, text, index, total):
    """Carrossel: capa com título grande; demais slides com faixa de texto e numeração."""
    pad = int(W * 0.06)
    if index == 0:
        f = font(["segoeuib.ttf", "arialbd.ttf"], int(W * 0.075))
        lines = wrap(d, text, f, W - 2 * pad)
        lh = int(f.size * 1.18)
        block = lh * len(lines) + pad
        for y in range(H - block - pad * 2, H):  # degradê escuro embaixo
            a = int(230 * min(1, (y - (H - block - pad * 2)) / (pad * 2)))
            d.line([(0, y), (W, y)], fill=(8, 4, 6, a))
        y = H - block
        d.rectangle([pad, y - pad // 2, pad + int(W * 0.12), y - pad // 2 + int(W * 0.0075)], fill=ACCENT + (255,))
        for ln in lines:
            d.text((pad, y), ln, font=f, fill=(255, 255, 255, 255))
            y += lh
    else:
        f = font(["segoeuib.ttf", "arialbd.ttf"], int(W * 0.047))
        lines = wrap(d, text, f, W - 2 * pad - 20)
        lh = int(f.size * 1.25)
        bh = lh * len(lines) + pad
        top = H - bh - pad // 2
        d.rounded_rectangle([pad // 2, top, W - pad // 2, H - pad // 2], radius=int(W * 0.026), fill=(10, 5, 8, 205))
        y = top + pad // 2
        for ln in lines:
            d.text((pad, y), ln, font=f, fill=(255, 255, 255, 255))
            y += lh
    # numeração "2/5"
    fn = font(["segoeuib.ttf", "arialbd.ttf"], int(W * 0.032))
    label = f"{index + 1}/{total}"
    tw = d.textlength(label, font=fn)
    d.rounded_rectangle([W - pad - tw - int(W * 0.026), pad - 4, W - pad, pad + fn.size + int(W * 0.013)],
                        radius=int(W * 0.02), fill=ACCENT + (235,))
    d.text((W - pad - tw - int(W * 0.013), pad + 2), label, font=fn, fill=(255, 255, 255, 255))


def _comic_layer(d, W, H, text):
    """HQ: balão de fala (Nome: fala) ou caixa de narração no topo do quadro."""
    s = W / 768
    f = font(["comicbd.ttf", "arialbd.ttf"], int(27 * s))
    m = re.match(r"^\s*([^:]{1,24}):\s*(.+)$", text)
    narration = m is None
    body = text if narration else f"{m.group(1).strip().upper()}: {m.group(2).strip()}"
    lines = wrap(d, body, f, W - int(80 * s))
    lh = int(34 * s)
    m16 = int(16 * s)
    box = [m16, m16, min(W - m16, m16 + int(40 * s) + int(max(d.textlength(l, font=f) for l in lines))),
           m16 + int(24 * s) + lh * len(lines)]
    fill = (255, 243, 176, 255) if narration else (255, 255, 255, 255)
    d.rounded_rectangle(box, radius=int((6 if narration else 22) * s), fill=fill, outline=(0, 0, 0, 255), width=max(2, int(3 * s)))
    if not narration:  # "rabinho" do balão
        x = box[0] + int(46 * s)
        d.polygon([(x, box[3] - 2), (x + int(26 * s), box[3] - 2), (x + int(6 * s), box[3] + int(26 * s))],
                  fill=fill, outline=(0, 0, 0, 255))
        d.line([(x + 2, box[3] - 2), (x + int(24 * s), box[3] - 2)], fill=fill, width=max(3, int(4 * s)))
    y = box[1] + int(12 * s)
    for ln in lines:
        d.text((box[0] + int(20 * s), y), ln, font=f, fill=(15, 15, 15, 255))
        y += lh


def _label_layer(d, W, H, text):
    """Evolução: etiqueta com o estágio no canto inferior."""
    s = W / 768
    f = font(["segoeuib.ttf", "arialbd.ttf"], int(34 * s))
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([int(22 * s), H - int(82 * s), int(22 * s) + tw + int(40 * s), H - int(22 * s)],
                        radius=int(30 * s), fill=(10, 5, 8, 215))
    d.text((int(42 * s), H - int(75 * s)), text, font=f, fill=(255, 255, 255, 255))


CAPTION_SIZE = {"slide": 1080, "comic": 768, "label": 768}


def caption_layer(kind, size, text, index, total):
    """Camada transparente só com o texto/balão, no tamanho pedido (usada nas imagens e no vídeo)."""
    W, H = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    mode = TYPES[kind]["captions"]
    if not text or mode not in CAPTION_SIZE:
        return layer
    d = ImageDraw.Draw(layer)
    {"slide": lambda: _slide_layer(d, W, H, text, index, total),
     "comic": lambda: _comic_layer(d, W, H, text),
     "label": lambda: _label_layer(d, W, H, text)}[mode]()
    return layer


def apply_caption(kind, img, text, index, total):
    mode = TYPES[kind]["captions"]
    if mode not in CAPTION_SIZE:
        return img.convert("RGB")  # movimento: sem texto; storyboard: o texto vai na folha, não no quadro
    base = upscale(img.convert("RGB"), CAPTION_SIZE[mode]).convert("RGBA")
    return Image.alpha_composite(base, caption_layer(kind, base.size, text, index, total)).convert("RGB")


# ============================ MONTAGENS ============================


def comic_page(panels, title):
    """Página de HQ em 2 colunas, com bordas pretas e título."""
    pw = 520
    panels = [upscale(p, pw) if p.size[0] != pw else p for p in panels]
    gut, head = 22, 96 if title else 22
    rows = [panels[i:i + 2] for i in range(0, len(panels), 2)]
    heights = [max(p.size[1] for p in r) for r in rows]
    W = gut * 3 + pw * 2
    H = head + sum(heights) + gut * (len(rows) + 1)
    page = Image.new("RGB", (W, H), (250, 248, 240))
    d = ImageDraw.Draw(page)
    if title:
        f = font(["comicbd.ttf", "impact.ttf", "arialbd.ttf"], 48)
        tw = d.textlength(title.upper(), font=f)
        d.text(((W - tw) / 2, 26), title.upper(), font=f, fill=(20, 20, 20))
    y = head
    for r, rh in zip(rows, heights):
        x = gut if len(r) == 2 else (W - pw) // 2   # quadro sozinho na última linha fica centralizado
        for p in r:
            page.paste(p, (x, y))
            d.rectangle([x - 2, y - 2, x + p.size[0] + 1, y + p.size[1] + 1], outline=(0, 0, 0), width=5)
            x += pw + gut
        y += rh + gut
    return page


def storyboard_sheet(frames, texts, title):
    """Folha de storyboard: 3 colunas, 'CENA N' + quadro + descrição."""
    cols, cw = 3, 400
    frames = [upscale(f, cw) for f in frames]
    fh = max(f.size[1] for f in frames)
    ft = font(["segoeui.ttf", "arial.ttf"], 19)
    fh_ = font(["segoeuib.ttf", "arialbd.ttf"], 20)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    text_h = max(len(wrap(probe, t or " ", ft, cw)) for t in texts) * 25 + 10
    cell_h = 34 + fh + 14 + text_h
    rows = (len(frames) + cols - 1) // cols
    gut, head = 30, 100
    W = gut + cols * (cw + gut)
    H = head + rows * (cell_h + gut)
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    d.text((gut, 30), (title or "Storyboard").upper(), font=font(["segoeuib.ttf", "arialbd.ttf"], 40), fill=(20, 20, 20))
    d.line([(gut, 86), (W - gut, 86)], fill=ACCENT, width=4)
    for i, (f, t) in enumerate(zip(frames, texts)):
        x = gut + (i % cols) * (cw + gut)
        y = head + (i // cols) * (cell_h + gut)
        d.text((x, y), f"CENA {i + 1}", font=fh_, fill=ACCENT)
        sheet.paste(f, (x, y + 34))
        d.rectangle([x - 1, y + 33, x + f.size[0], y + 34 + f.size[1]], outline=(30, 30, 30), width=2)
        ty = y + 34 + fh + 14
        for ln in wrap(d, t or "", ft, cw):
            d.text((x, ty), ln, font=ft, fill=(60, 60, 60))
            ty += 25
    return sheet


def strip(frames, labels=None):
    """Tira horizontal (até 6 por linha) sobre fundo escuro."""
    fw = 360
    frames = [upscale(f, fw) for f in frames]
    per = min(6, len(frames))
    rows = (len(frames) + per - 1) // per
    fh = max(f.size[1] for f in frames)
    gut = 16
    W = gut + per * (fw + gut)
    H = gut + rows * (fh + gut)
    out = Image.new("RGB", (W, H), (14, 8, 11))
    for i, f in enumerate(frames):
        out.paste(f, (gut + (i % per) * (fw + gut), gut + (i // per) * (fh + gut)))
    return out


def save_gif(frames, path, ms):
    frames = [f.convert("RGB").resize(frames[0].size, Image.LANCZOS) for f in frames]
    pal = [f.quantize(colors=256, method=Image.MEDIANCUT) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=ms, loop=0, optimize=True)


def build_outputs(seq_dir, ctx, finals, raws):
    """Monta a montagem final, o GIF e o ZIP. Retorna as URLs."""
    kind, plan = ctx["type"], ctx["plan"]
    texts = [f.get("text", "") for f in plan["frames"]]
    out = {}
    if kind == "hq":
        comp = comic_page(finals, plan.get("title", ""))
    elif kind == "storyboard":
        comp = storyboard_sheet(finals, texts, plan.get("title", ""))
    else:
        comp = strip(finals)
    comp.save(seq_dir / "montagem.png")
    out["composite"] = "montagem.png"
    if TYPES[kind].get("gif_ms"):
        save_gif(finals if kind == "evolucao" else raws, seq_dir / "animacao.gif", TYPES[kind]["gif_ms"])
        out["gif"] = "animacao.gif"
    with zipfile.ZipFile(seq_dir / "sequencia.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(len(finals)):
            z.write(seq_dir / f"quadro_{i + 1:02d}.png", f"quadro_{i + 1:02d}.png")
        for name in out.values():
            z.write(seq_dir / name, name)
        z.writestr("plano.json", json.dumps(plan, ensure_ascii=False, indent=2))
    out["zip"] = "sequencia.zip"
    return out

# ============================ GERAÇÃO ============================


def url(seq_id, name):
    return f"/api/image-file/sequences/{seq_id}/{name}"


def ip_scale(mode, consistency):
    return {"character": 0.3 + 0.5 * consistency, "style": 0.15 + 0.4 * consistency,
            "chain": 0.1 + 0.4 * consistency}[mode]


def render_frame(ctx, index, raws, job, progress):
    """Gera o quadro `index` (imagem crua, sem texto)."""
    kind, plan = ctx["type"], ctx["plan"]
    t = TYPES[kind]
    frame = plan["frames"][index]
    prompt = build_prompt(plan, frame, ctx["style_extra"], g.engine.pipe.tokenizer)
    fast, steps = ctx["fast"], ctx["steps"]
    seed = ctx["seed"] + ctx.get("seed_offsets", {}).get(str(index), 0)
    if t["consistency"] == "chain":
        # partindo de uma imagem quase igual, o mesmo ruído repetiria a mesma pose
        seed += index
    mode = "txt2img"
    call = dict(prompt=prompt, negative_prompt=ctx["negative"], guidance_scale=ctx["guidance"],
                generator=torch.Generator("cpu").manual_seed(seed))
    run_steps = steps
    if t["consistency"] == "chain" and index > 0:
        mode = "img2img"
        strength = t["strength"] * (1.25 - 0.5 * ctx["consistency"])
        steps = max(steps, int(-(-(3 if fast else 8) // strength)))
        run_steps = max(1, int(steps * strength))
        call.update(image=raws[index - 1], strength=strength)
    else:
        call.update(width=ctx["width"], height=ctx["height"])
    call["num_inference_steps"] = steps

    ref = ctx.get("reference")
    if ref is None and index > 0 and raws:
        ref = raws[0]
    use_ip = ctx["ip"] and ref is not None
    if use_ip:
        g.engine.ip_on(ip_scale(t["consistency"], ctx["consistency"]))
        call["ip_adapter_image"] = ref
    else:
        g.engine.ip_off()
    if g.MODELS[ctx["model"]].get("clip_skip"):
        call["clip_skip"] = g.MODELS[ctx["model"]]["clip_skip"]

    def on_step(pipe, step, timestep, kwargs):
        if job["cancel"]:
            raise g.Cancelled()
        progress(min(step + 1, run_steps) / run_steps)
        return kwargs

    call["callback_on_step_end"] = on_step
    print(f"🎞️  [{kind} {index + 1}/{len(plan['frames'])} {mode}{' +ref' if use_ip else ''}] {prompt}")
    return g.engine.pipeline_for(mode)(**call).images[0]


def finish_frame(seq_dir, ctx, index, raw):
    raw.save(seq_dir / f"cru_{index + 1:02d}.png")
    frames = ctx["plan"]["frames"]
    final = apply_caption(ctx["type"], raw, frames[index].get("text", "") if ctx["captions"] else "",
                          index, len(frames))
    final.save(seq_dir / f"quadro_{index + 1:02d}.png")
    return final


def result_of(ctx, seq_dir, outputs=None, done=None):
    n = len(ctx["plan"]["frames"])
    stamp = int(time.time())
    frames = []
    for i in range(n):
        p = seq_dir / f"quadro_{i + 1:02d}.png"
        frames.append({"index": i, "text": ctx["plan"]["frames"][i].get("text", ""),
                       "narration": ctx["plan"]["frames"][i].get("narration", ""),
                       "prompt": ctx["plan"]["frames"][i].get("prompt", ""),
                       "url": url(ctx["id"], p.name) + f"?v={stamp}" if p.exists() else None})
    res = {"seq_id": ctx["id"], "type": ctx["type"], "type_name": TYPES[ctx["type"]]["name"],
           "title": ctx["plan"].get("title", ""), "frames": frames, "model_name": g.MODELS[ctx["model"]]["name"],
           "seed": ctx["seed"], "done": done if done is not None else n}
    outputs = dict(outputs or {})
    if (seq_dir / "video.mp4").exists():
        outputs["video"] = "video.mp4"
    for key, name in outputs.items():
        res[key] = url(ctx["id"], name) + f"?v={stamp}"
    if ctx.get("video_info"):
        res["video_info"] = ctx["video_info"]
    return res


def make_video(job, ctx, seq_dir, base=0.0, span=1.0):
    """Cria o vídeo narrado e o coloca no .zip. base/span: faixa da barra de progresso."""
    import narrated_video
    def progress(frac, msg):
        g.update(job, status="gerando", percent=int(100 * (base + span * frac)), message=msg)
    name, voice_name, seconds = narrated_video.build_video(
        seq_dir, ctx, ctx.get("voice", "francisca"), ctx.get("rate", 0), progress, lambda: job["cancel"])
    ctx["video_info"] = {"voice": voice_name, "seconds": seconds}
    save_context(seq_dir, ctx)
    with zipfile.ZipFile(seq_dir / "sequencia.zip", "a", zipfile.ZIP_DEFLATED) as z:
        if name not in z.namelist():
            z.write(seq_dir / name, name)
    return name


def prepare_context(p):
    kind = p.get("type")
    if kind not in TYPES:
        raise ValueError("Tipo de sequência inválido.")
    plan = p.get("plan") or {}
    frames = [{"prompt": str(f.get("prompt", "")).strip(), "text": str(f.get("text", "")).strip(),
               "narration": str(f.get("narration", "")).strip()}
              for f in plan.get("frames", []) if str(f.get("prompt", "")).strip()]
    if len(frames) < 2:
        raise ValueError("A sequência precisa de pelo menos 2 quadros com descrição.")
    plan = {**plan, "frames": frames[:TYPES[kind]["max"]]}
    check_plan(plan)
    installed = ollama_models()   # quadros escritos/editados em português pelo usuário também são traduzidos
    model = next((m for m in PLAN_MODELS if m in installed), None)
    if model:
        ensure_english(plan, model)

    reference = p.get("_reference")  # PIL já decodificada pelo /generate
    if reference is not None and g.violates_real_photo_rule(plan_text(plan)):
        raise ValueError(g.REAL_PHOTO_MSG)

    style = p.get("style") or "auto"
    if style == "auto":
        # o estilo visual já vem na ficha do plano; aqui só entram etiquetas neutras de qualidade
        # (as do preset, como "dramatic lighting", brigavam com pedidos como "bright and cheerful")
        style = g.CATEGORY_STYLE.get(plan.get("category"), "arte")
        _, extra_neg, preferred = g.STYLES[style]
        extra = ", best quality, highly detailed"
    else:
        extra, extra_neg, preferred = g.STYLES.get(style, g.STYLES["nenhum"])
    model = p.get("model") or "auto"
    if model == "auto" or model not in g.MODELS:
        model = preferred or g.DEFAULT_MODEL
    available = g.engine.available()
    if not available.get(model):
        model = next((k for k, ok in available.items() if ok), None)
    fast = bool(p.get("turbo", True))
    width, height = g.SIZES.get(p.get("size"), g.SIZES["quadrado"])
    seed = p.get("seed")
    seed = int(seed) if str(seed or "").strip().isdigit() else random.randint(0, 2**32 - 1)
    consistency = max(0.0, min(1.0, float(p.get("consistency", 0.6))))
    return {
        "id": f"seq_{time.strftime('%Y%m%d_%H%M%S')}", "type": kind, "plan": plan, "model": model, "style": style,
        "style_extra": extra, "negative": ", ".join(x for x in (g.BASE_NEGATIVE, extra_neg, p.get("negative", "")) if x),
        "fast": fast, "steps": int(p.get("steps") or (6 if fast else 25)), "guidance": 1.5 if fast else 7.0,
        "width": width, "height": height, "seed": seed, "consistency": consistency,
        "captions": bool(p.get("captions", True)) and TYPES[kind]["captions"] is not None,
        "ip": bool(p.get("use_ip", True)) and g.engine.ip_available() and consistency > 0,
        "reference": reference, "seed_offsets": {},
        "narrate": bool(p.get("narrate")), "voice": p.get("voice") or "francisca", "rate": int(p.get("rate") or 0),
    }


def save_context(seq_dir, ctx):
    data = {k: v for k, v in ctx.items() if k != "reference"}
    (seq_dir / "sequencia.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if ctx.get("reference") is not None:
        ctx["reference"].save(seq_dir / "referencia.png")


def load_context(seq_id):
    seq_dir = g.OUTPUT_DIR / "sequences" / Path(seq_id).name
    ctx = json.loads((seq_dir / "sequencia.json").read_text(encoding="utf-8"))
    ref = seq_dir / "referencia.png"
    ctx["reference"] = Image.open(ref).convert("RGB") if ref.exists() else None
    return seq_dir, ctx


def load_raws(seq_dir, n):
    raws = []
    for i in range(n):
        p = seq_dir / f"cru_{i + 1:02d}.png"
        raws.append(Image.open(p).convert("RGB") if p.exists() else None)
    return raws


def generate_range(job, ctx, seq_dir, start, end, raws, finals, t0):
    """Gera os quadros [start, end) em ordem, atualizando o progresso e o resultado parcial."""
    n = len(ctx["plan"]["frames"])
    todo = end - start
    with g.engine.lock:
        if g.engine.key != ctx["model"]:
            g.update(job, status="carregando", percent=2, message=f"Carregando {g.MODELS[ctx['model']]['name']}...")
        g.engine.load(ctx["model"])
        g.engine.ip_off()
        g.engine.set_fast(ctx["fast"])
        try:
            for i in range(start, end):
                if job["cancel"]:
                    raise g.Cancelled()
                frame_start = time.time()

                def progress(frac, i=i):
                    elapsed = time.time() - t0
                    done = (i - start) + frac
                    left = elapsed / max(done, 0.05) * (todo - done)
                    g.update(job, status="gerando", percent=3 + int(95 * done / todo),
                             message=f"Quadro {i + 1}/{n} · faltam ~{int(left // 60)}min{int(left % 60):02d}s")

                progress(0)
                raw = render_frame(ctx, i, raws, job, progress)
                raws.append(raw)
                finals.append(finish_frame(seq_dir, ctx, i, raw))
                g.update(job, result=result_of(ctx, seq_dir, done=i + 1))
                print(f"✅ Quadro {i + 1}/{n} em {time.time() - frame_start:.0f}s")
        finally:
            g.engine.ip_off()


def finish_sequence(job, ctx, seq_dir, finals, raws, t0):
    g.update(job, message="Montando a sequência...")
    outputs = build_outputs(seq_dir, ctx, finals, raws)
    if ctx.get("narrate"):
        try:
            outputs["video"] = make_video(job, ctx, seq_dir, 0.9, 0.1)
        except InterruptedError:
            raise g.Cancelled()
    seconds = round(time.time() - t0)
    res = result_of(ctx, seq_dir, outputs)
    res["seconds"] = seconds
    print(f"🎬 Sequência {ctx['id']} pronta em {seconds}s")
    g.update(job, status="concluído", percent=100, finished=time.time(),
             message=f"Sequência pronta em {seconds // 60}min{seconds % 60:02d}s", result=res)


def run_sequence(job):
    """Job de sequência: completa, ou só o 1º quadro se params.preview (prévia para aprovar antes)."""
    p = job["params"]
    t0 = time.time()
    g.update(job, status="preparando", started=t0, percent=1, message="Preparando a sequência...")
    ctx = prepare_context(p)
    seq_dir = g.OUTPUT_DIR / "sequences" / ctx["id"]
    seq_dir.mkdir(parents=True, exist_ok=True)
    save_context(seq_dir, ctx)
    n = len(ctx["plan"]["frames"])
    raws, finals = [], []
    end = 1 if p.get("preview") else n
    generate_range(job, ctx, seq_dir, 0, end, raws, finals, t0)
    if end < n:
        res = result_of(ctx, seq_dir, done=end)
        res["partial"] = True
        g.update(job, status="concluído", percent=100, finished=time.time(), result=res,
                 message="Prévia do 1º quadro pronta. Refaça até gostar e depois clique em Continuar.")
        return
    finish_sequence(job, ctx, seq_dir, finals, raws, t0)


def run_continue(job):
    """Gera os quadros que faltam de uma sequência já começada (depois da prévia)."""
    t0 = time.time()
    seq_dir, ctx = load_context(job["params"]["seq_id"])
    g.update(job, status="preparando", started=t0, percent=1, message="Continuando a sequência...")
    n = len(ctx["plan"]["frames"])
    raws = load_raws(seq_dir, n)
    start = next((i for i, r in enumerate(raws) if r is None), n)
    raws = raws[:start]
    finals = [Image.open(seq_dir / f"quadro_{i + 1:02d}.png").convert("RGB") for i in range(start)]
    generate_range(job, ctx, seq_dir, start, n, raws, finals, t0)
    finish_sequence(job, ctx, seq_dir, finals, raws, t0)


def run_regenerate(job):
    """Refaz um quadro (nova semente e/ou nova descrição) e remonta tudo."""
    p = job["params"]
    t0 = time.time()
    seq_dir, ctx = load_context(p["seq_id"])
    index = int(p["index"])
    n = len(ctx["plan"]["frames"])
    if not 0 <= index < n:
        raise ValueError("Quadro inexistente.")
    frame = ctx["plan"]["frames"][index]
    if p.get("prompt"):
        frame["prompt"] = str(p["prompt"]).strip()
    if p.get("text") is not None:
        frame["text"] = str(p["text"]).strip()
    if p.get("narration") is not None:
        frame["narration"] = str(p["narration"]).strip()
    check_plan(ctx["plan"])
    if ctx.get("reference") is not None and g.violates_real_photo_rule(plan_text(ctx["plan"])):
        raise ValueError(g.REAL_PHOTO_MSG)
    if p.get("new_seed", True):
        ctx["seed_offsets"][str(index)] = random.randint(1, 10**6)

    g.update(job, status="gerando", started=t0, percent=3, message=f"Refazendo o quadro {index + 1}...")
    raws = load_raws(seq_dir, n)
    with g.engine.lock:
        g.engine.load(ctx["model"])
        g.engine.ip_off()
        g.engine.set_fast(ctx["fast"])
        try:
            def progress(frac):
                g.update(job, percent=3 + int(90 * frac), message=f"Refazendo o quadro {index + 1} · {int(frac * 100)}%")
            raw = render_frame(ctx, index, raws[:index], job, progress)
        finally:
            g.engine.ip_off()
    raws[index] = raw
    finish_frame(seq_dir, ctx, index, raw)
    (seq_dir / "video.mp4").unlink(missing_ok=True)   # o vídeo antigo ficou desatualizado
    ctx.pop("video_info", None)
    save_context(seq_dir, ctx)
    if any(r is None for r in raws):   # ainda na prévia: só atualiza o quadro
        res = result_of(ctx, seq_dir, done=sum(r is not None for r in raws))
        res["partial"] = True
    else:
        finals = [Image.open(seq_dir / f"quadro_{i + 1:02d}.png").convert("RGB") for i in range(n)]
        res = result_of(ctx, seq_dir, build_outputs(seq_dir, ctx, finals, raws))
    res["seconds"] = round(time.time() - t0)
    g.update(job, status="concluído", percent=100, finished=time.time(),
             message=f"Quadro {index + 1} refeito em {res['seconds']}s", result=res)


def run_video(job):
    """Cria (ou refaz) o vídeo narrado de uma sequência pronta, com a voz e as narrações escolhidas."""
    p = job["params"]
    t0 = time.time()
    seq_dir, ctx = load_context(p["seq_id"])
    frames = ctx["plan"]["frames"]
    for i, text in enumerate(p.get("narrations") or []):
        if i < len(frames) and text is not None:
            frames[i]["narration"] = str(text).strip()
    check_plan(ctx["plan"])
    ctx["voice"] = p.get("voice") or ctx.get("voice", "francisca")
    ctx["rate"] = int(p.get("rate") or 0)
    ctx["narrate"] = True
    g.update(job, status="gerando", started=t0, percent=1, message="Preparando o vídeo...")
    try:
        make_video(job, ctx, seq_dir)
    except InterruptedError:
        raise g.Cancelled()
    res = result_of(ctx, seq_dir, {"composite": "montagem.png", "zip": "sequencia.zip",
                                   **({"gif": "animacao.gif"} if (seq_dir / "animacao.gif").exists() else {})})
    res["seconds"] = round(time.time() - t0)
    g.update(job, status="concluído", percent=100, finished=time.time(), result=res,
             message=f"Vídeo pronto ({ctx['video_info']['seconds']:.0f}s de duração) em {res['seconds']}s")
