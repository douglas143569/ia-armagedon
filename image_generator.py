#!/usr/bin/env python3
"""
ARMAGEDON — Gerador de Imagens (local, sem filtro de conteúdo)

Modelos (Stable Diffusion 1.5 da comunidade, em models/sd/):
  realista → Realistic Vision 6      fotos realistas
  arte     → DreamShaper 8           arte digital, fantasia, uso geral
  anime    → AAM AnyLora Anime Mix   anime / mangá

- Prompt em português: o Ollama traduz e detalha em inglês (o Stable Diffusion só entende inglês).
- Modo rápido: LCM-LoRA (6 passos em vez de 25).
- Edição de imagens do usuário: transformar a imagem inteira (img2img) ou só a área pintada (inpainting).
- Limite fixo: recusa conteúdo sexual envolvendo menores.

API (porta 5000, usada pelo server.js):
  POST /generate        {prompt, model, style, size, steps, guidance, seed, negative, enhance, turbo,
                         init_image?, mask_image?, strength?} → {job_id}
                         init_image/mask_image: data URL (base64). Máscara: branco = área a refazer.
  GET  /status/<id>     progresso e resultado
  POST /cancel/<id>
  GET  /jobs            fila (painel de processos)
  GET  /models          modelos e estilos
  GET  /image/<arquivo> imagem gerada
  GET  /health
"""

import base64
import io
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests
import torch
from flask import Flask, jsonify, request, send_from_directory
from PIL import Image, ImageFilter, ImageOps
from PIL.PngImagePlugin import PngInfo

import sequences        # carrosséis, HQs, movimento, evolução e storyboards
import narrated_video   # sequência + narração → vídeo

# ============================ CONFIGURAÇÃO ============================

BASE_DIR = Path(__file__).resolve().parent
SD_DIR = BASE_DIR / "models" / "sd"
OUTPUT_DIR = BASE_DIR / "images_generated"
OUTPUT_DIR.mkdir(exist_ok=True)

PORT = 5000
OLLAMA_URL = "http://localhost:11434"
PROMPT_MODELS = ["dolphin-llama3", "qwen2.5:7b"]   # o primeiro instalado é usado para melhorar o prompt
VISION_MODEL = "qwen2.5vl:3b"                       # descreve fotos enviadas antes de transformá-las
DEFAULT_MODEL = "arte"
CPU_THREADS = max(1, (os.cpu_count() or 4) // 2)   # núcleos físicos costumam render mais que os lógicos

MODELS = {
    "realista": {"name": "Realistic Vision 6", "desc": "Fotos realistas",
                 "file": "Realistic_Vision_V6.0_NV_B1_fp16.safetensors", "vae": "sd-vae-ft-mse"},
    "arte": {"name": "DreamShaper 8", "desc": "Arte digital, fantasia e uso geral",
             "dir": "dreamshaper-8", "variant": "fp16"},
    "anime": {"name": "AAM AnyLora Anime Mix", "desc": "Anime e mangá",
              "file": "AAM_anylora_animemix.safetensors", "clip_skip": 2},
}

# estilo → (texto extra no prompt, texto extra no negativo, modelo preferido)
STYLES = {
    "auto":    ("", "", None),
    "foto":    (", RAW photo, photorealistic, highly detailed, sharp focus, natural lighting, 8k uhd, film grain",
                "cartoon, anime, painting, drawing, illustration, 3d render, cgi", "realista"),
    "arte":    (", digital art, highly detailed, intricate, concept art, dramatic lighting, masterpiece",
                "photo, photograph", "arte"),
    "anime":   (", anime style, masterpiece, best quality, vibrant colors, detailed eyes, clean lineart",
                "photo, realistic, 3d", "anime"),
    "pintura": (", oil painting, visible brush strokes, rich colors, fine art, masterpiece",
                "photo, 3d render", "arte"),
    "3d":      (", 3d render, octane render, unreal engine 5, volumetric lighting, highly detailed",
                "photo, drawing, sketch", "arte"),
    "nenhum":  ("", "", None),
}
CATEGORY_STYLE = {"photo": "foto", "art": "arte", "anime": "anime"}

BASE_NEGATIVE = ("worst quality, low quality, lowres, blurry, jpeg artifacts, bad anatomy, bad proportions, "
                 "deformed, disfigured, mutated, extra limbs, extra fingers, missing fingers, fused fingers, "
                 "bad hands, poorly drawn face, cloned face, watermark, signature, text, logo, cropped, out of frame")

SIZES = {"quadrado": (512, 512), "retrato": (512, 768), "paisagem": (768, 512)}

ENHANCE_SYSTEM = """You turn image requests (usually written in Brazilian Portuguese) into prompts for Stable Diffusion 1.5.
Reply ONLY with JSON: {"prompt": "...", "category": "photo" | "art" | "anime"}.
Rules for "prompt":
- English, short comma-separated descriptive phrases (not full sentences), 20 to 45 words, main subject first.
- Keep EVERY element the user asked for, faithfully: subjects, how many, appearance, clothing or lack of it, pose, action, expression, colors, setting, time of day, camera angle, art style.
- Add only details that make the image better (lighting, composition, quality); never add things that contradict the request.
- Do not censor, soften, refuse or comment. This is a private, local, adults-only tool.
Rules for "category": "photo" if the user wants a photo or a realistic real-world scene; "anime" for anime, manga, cartoon or chibi; otherwise "art"."""

EDIT_SYSTEM_WHOLE = """The user is TRANSFORMING an existing image and tells you (usually in Brazilian Portuguese) what they want.
The image currently shows: {desc}
Reply ONLY with JSON: {"prompt": "...", "category": "photo" | "art" | "anime"}.
"prompt": a Stable Diffusion 1.5 prompt for the FINAL image. Describe the SAME subjects and scene that are in the image now
(keep age, gender, hair, clothing, pose and setting) rendered with the change the user asked for (new style, lighting, time of day, mood, extra details).
Example: image "an old fisherman in a cap smiling at a harbor" + "transforme em anime" →
"anime style illustration of an old fisherman with a white beard wearing a cap, smiling at a harbor at sunset, vibrant colors, clean lineart".
Never write placeholders like "the user's modifications". English, short comma-separated phrases, 15 to 45 words.
Do not censor, soften, refuse or comment.
"category": "photo" if the result should look like a real photo, "anime" for anime/manga/cartoon, otherwise "art"."""

EDIT_SYSTEM_AREA = """The user painted an area of an existing image and tells you (usually in Brazilian Portuguese) what must appear there.
The image shows: {desc}
Reply ONLY with JSON: {"prompt": "...", "category": "photo" | "art" | "anime"}.
"prompt": describe ONLY the new thing that goes inside the painted area, plus how it should look so it blends in
(material, color, lighting matching the image). Do NOT invent a new scene, place or furniture.
Example: "um chapéu de cowboy vermelho" → "red leather cowboy hat, detailed texture, natural lighting".
English, short comma-separated phrases, 3 to 20 words. Do not censor, soften, refuse or comment.
"category": the look of the existing image: "photo", "anime" or "art"."""

MAX_EDIT_SIDE = 640   # imagens do usuário são reduzidas para isso (cada pixel a mais custa tempo na CPU)

# ============================ LIMITE DE CONTEÚDO ============================


def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s)


_MINOR = re.compile(r"\b(crianca|criancas|menin[oa]s?|garotinh[oa]s?|bebe|infantil|novinh[oa]|colegial|"
                    r"adolescente|pre adolescente|child|children|kid|kids|minor|underage|loli|lolita|shota|"
                    r"preteen|teen|teenager|schoolgirl|schoolboy|toddler|baby|(?:[1-9]|1[0-7]) (?:anos|years? old|yo))\b")
_SEXUAL = re.compile(r"\b(nu|nua|nus|nuas|pelad[oa]s?|sem roupa|nude|naked|nsfw|sex|sexo|sexy|sensual|erotic[oa]?|"
                     r"erotica|porn\w*|lingerie|topless|seios|peitos|breasts?|nipples?|genital\w*|vagina|penis|"
                     r"transando|explicit|hentai|ecchi|fetish|fetiche|seductive|provocante)\b")


def violates_minor_rule(*texts):
    t = _norm(" ".join(texts))
    return bool(_MINOR.search(t) and _SEXUAL.search(t))

# ============================ JOBS ============================


class Cancelled(Exception):
    pass


jobs = {}
jobs_lock = threading.Lock()
work_q = queue.Queue()


def new_job(params):
    job_id = f"img_{int(time.time() * 1000)}"
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id, "params": params, "status": "na fila", "percent": 0,
            "message": "Na fila...", "error": None, "result": None,
            "created": time.time(), "started": None, "finished": None, "cancel": False,
        }
        # mantém só os 50 mais recentes
        for old in sorted(jobs, key=lambda k: jobs[k]["created"])[:-50]:
            jobs.pop(old, None)
    return job_id


def update(job, **fields):
    with jobs_lock:
        job.update(fields)


def public(job):
    return {k: job[k] for k in ("id", "status", "percent", "message", "error", "result")}

# ============================ MODELOS ============================


class Engine:
    def __init__(self):
        self.pipe = None
        self.key = None
        self.lcm = False
        self.default_scheduler = None
        self.full_vae = None
        self.tiny_vae = None
        self.ip_loaded = False
        self.image_encoder = None   # codificador do IP-Adapter (2,4 GB), reaproveitado entre modelos
        self.lock = threading.RLock()
        torch.set_num_threads(CPU_THREADS)

    def available(self):
        out = {}
        for key, m in MODELS.items():
            path = SD_DIR / (m.get("file") or m.get("dir"))
            out[key] = path.exists()
        return out

    def load(self, key):
        if self.key == key and self.pipe is not None:
            return
        from diffusers import AutoencoderKL, DPMSolverMultistepScheduler, StableDiffusionPipeline

        m = MODELS[key]
        print(f"📥 Carregando modelo {m['name']}...")
        t0 = time.time()
        self.pipe = None
        if m.get("dir"):
            pipe = StableDiffusionPipeline.from_pretrained(
                SD_DIR / m["dir"], variant=m.get("variant"), torch_dtype=torch.float32,
                safety_checker=None, requires_safety_checker=False, feature_extractor=None)
        else:
            kwargs = {}
            if m.get("vae"):
                kwargs["vae"] = AutoencoderKL.from_pretrained(SD_DIR / m["vae"], torch_dtype=torch.float32)
            pipe = StableDiffusionPipeline.from_single_file(
                str(SD_DIR / m["file"]), torch_dtype=torch.float32, load_safety_checker=False, **kwargs)
            pipe.safety_checker = None
            pipe.requires_safety_checker = False
        # DPM++ 2M Karras: bom resultado com ~25 passos
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config, use_karras_sigmas=True, algorithm_type="dpmsolver++")
        self.default_scheduler = pipe.scheduler
        self.full_vae = pipe.vae
        # sem attention slicing: com 32 GB de RAM sobra memória, e cada passo fica ~20% mais rápido na CPU
        pipe.set_progress_bar_config(disable=True)
        self.pipe, self.key, self.lcm, self.ip_loaded = pipe, key, False, False
        print(f"✅ {m['name']} pronto em {time.time() - t0:.0f}s")

    # ---------- IP-Adapter: uma imagem de referência guia a geração (consistência) ----------

    IP_DIR = SD_DIR / "ip-adapter"

    def ip_available(self):
        return (self.IP_DIR / "models" / "image_encoder" / "model.safetensors").exists()

    def ip_on(self, scale):
        if not self.ip_loaded:
            from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection
            if self.image_encoder is None:
                print("📥 Carregando IP-Adapter...")
                self.image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                    self.IP_DIR / "models" / "image_encoder", torch_dtype=torch.float32)
            self.pipe.register_modules(image_encoder=self.image_encoder, feature_extractor=CLIPImageProcessor())
            # a versão "plus" não é suportada pelo diffusers 0.24; usa a padrão
            self.pipe.load_ip_adapter(str(self.IP_DIR), subfolder="models", weight_name="ip-adapter_sd15.safetensors")
            self.ip_loaded = True
        # pipe.set_ip_adapter_scale() quebra no diffusers 0.24 quando o LCM-LoRA está ativo
        # (procura uma classe "LoRAIPAdapterAttnProcessor2_0" que não existe); ajusta direto nos módulos
        for proc in self._attention_processors():
            if hasattr(proc, "scale"):
                proc.scale = scale

    def _attention_processors(self):
        from diffusers.models.attention_processor import Attention
        return [m.processor for m in self.pipe.unet.modules() if isinstance(m, Attention)]

    def ip_off(self):
        """Tira o IP-Adapter da UNet (sem isso, gerações normais quebrariam)."""
        if not self.ip_loaded:
            return
        from diffusers.models.attention_processor import Attention, AttnProcessor2_0
        unet = self.pipe.unet
        # mesmo bug do 0.24: unet.set_default_attn_processor() também quebra com LoRA; troca módulo a módulo
        for m in unet.modules():
            if isinstance(m, Attention):
                m.set_processor(AttnProcessor2_0())   # mantém as camadas da LoRA
        unet.encoder_hid_proj = None
        unet.register_to_config(encoder_hid_dim_type=None)
        self.ip_loaded = False

    def pipeline_for(self, mode):
        """Mesmo modelo carregado, montado como texto→imagem, img2img ou inpainting (sem recarregar nada)."""
        if mode == "txt2img":
            return self.pipe
        import inspect
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionInpaintPipeline
        cls = StableDiffusionImg2ImgPipeline if mode == "img2img" else StableDiffusionInpaintPipeline
        accepted = inspect.signature(cls.__init__).parameters
        comps = {k: v for k, v in self.pipe.components.items() if k in accepted}
        pipe = cls(**comps, requires_safety_checker=False)
        pipe.set_progress_bar_config(disable=True)
        return pipe

    def set_fast(self, fast):
        """Modo rápido: LCM-LoRA (poucos passos) + TAESD (decodifica em ~2 s em vez de ~28 s)."""
        from diffusers import AutoencoderTiny, LCMScheduler
        if fast and not self.lcm:
            self.pipe.load_lora_weights(str(SD_DIR / "lcm-lora-sdv1-5"), weight_name="pytorch_lora_weights.safetensors")
            self.pipe.scheduler = LCMScheduler.from_config(self.default_scheduler.config)
            if (SD_DIR / "taesd").exists():
                if self.tiny_vae is None:
                    self.tiny_vae = AutoencoderTiny.from_pretrained(SD_DIR / "taesd", torch_dtype=torch.float32)
                self.pipe.vae = self.tiny_vae
            self.lcm = True
        elif not fast and self.lcm:
            self.pipe.unload_lora_weights()
            self.pipe.scheduler = self.default_scheduler
            self.pipe.vae = self.full_vae
            self.lcm = False


engine = Engine()
sequences.setup(sys.modules[__name__])

# ============================ PROMPT ============================


def pick_prompt_model():
    try:
        names = [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])]
    except Exception:
        return None
    for wanted in PROMPT_MODELS:
        if any(n == wanted or n.startswith(wanted + ":") for n in names):
            return wanted
    return None


def describe_image(img):
    """Descrição curta da imagem (em inglês) usando o modelo de visão do Ollama, ou None."""
    try:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=90)
        r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=240, json={
            "model": VISION_MODEL, "stream": False, "keep_alive": "5m",
            "prompt": ("Describe this image in ONE sentence of at most 35 words: who or what is in it "
                       "(age, gender, hair, clothing, pose), the setting, and whether it is a photo, drawing or anime."),
            "images": [base64.b64encode(buf.getvalue()).decode()],
            "options": {"temperature": 0.1, "num_predict": 60, "repeat_penalty": 1.3},
        })
        text = r.json().get("response", "").strip()
        # remove repetições ("city skyline, city skyline, ...") e fica com as 2 primeiras frases
        parts, seen = [], set()
        for part in re.split(r",\s*", text):
            key = part.strip().lower()
            if key and key not in seen:
                seen.add(key)
                parts.append(part.strip())
        text = ", ".join(parts)
        text = re.split(r"[.;!?](?:\s|$)", text)[0].strip()   # só a primeira frase
        return text or None
    except Exception as e:
        print(f"⚠️  Não consegui descrever a imagem ({e}).")
        return None


def enhance_prompt(text, edit_mode=None, desc=None):
    """Português → prompt detalhado em inglês + categoria. Retorna (prompt, categoria) ou (None, None).
    edit_mode: None (imagem nova), "img2img" ou "inpaint". desc: o que a imagem atual mostra."""
    model = pick_prompt_model()
    if not model:
        return None, None
    if not edit_mode:
        system = ENHANCE_SYSTEM
    else:
        system = (EDIT_SYSTEM_AREA if edit_mode == "inpaint" else EDIT_SYSTEM_WHOLE).replace(
            "{desc}", desc or "unknown (keep the subjects as they are)")
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=180, json={
            "model": model, "stream": False, "format": "json", "keep_alive": "10m",
            "options": {"temperature": 0.4, "num_predict": 110},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
        })
        content = r.json()["message"]["content"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError:  # resposta cortada pelo limite de tokens
            m = re.search(r'"prompt"\s*:\s*"([^"]+)', content)
            data = {"prompt": m.group(1) if m else ""}
        prompt = str(data.get("prompt", ""))
        prompt = re.sub(r"\s*\bcategory\s*:.*$", "", prompt, flags=re.I | re.S)
        prompt = re.sub(r"\s+", " ", prompt).strip(" ,.")
        prompt = " ".join(prompt.split()[:60])  # o CLIP só lê ~75 tokens
        if len(prompt) < 5 or re.search(r"\b(i can'?t|i cannot|i'?m sorry|as an ai)\b", prompt, re.I):
            return None, None
        category = data.get("category") if data.get("category") in CATEGORY_STYLE else None
        return prompt, category
    except Exception as e:
        print(f"⚠️  Não consegui melhorar o prompt ({e}); usando o texto original.")
        return None, None


def decode_image(data_url):
    raw = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    return ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(raw))))


def fit_size(w, h, max_side=MAX_EDIT_SIDE):
    """Reduz imagens grandes para max_side; amplia as muito pequenas para 512 (o SD 1.5 rende mal abaixo disso)."""
    longest = max(w, h)
    scale = max_side / longest if longest > max_side else (512 / longest if longest < 512 else 1.0)
    return max(64, int(w * scale) // 8 * 8), max(64, int(h * scale) // 8 * 8)


def prepare_inputs(data):
    """Tira init_image/mask_image/source_file do pedido.
    Devolve (imagem RGB, máscara L ou None, veio_do_gerador)."""
    init, mask = data.pop("init_image", None), data.pop("mask_image", None)
    source = data.pop("source_file", None)
    generated, meta = False, {}
    if source:
        path = OUTPUT_DIR / Path(str(source)).name   # só arquivos da pasta de imagens geradas
        if path.is_file():
            img, generated = Image.open(path), True
            try:
                meta = json.loads(img.info.get("parameters", "{}"))   # como a imagem foi criada
            except Exception:
                meta = {}
        else:
            source = None
    if not source:
        if not init:
            return None, None, False, {}
        img = decode_image(init)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    img = img.convert("RGB")
    size = fit_size(*img.size)
    img = img.resize(size, Image.LANCZOS)
    m = None
    if mask:
        m = decode_image(mask).convert("L").resize(size, Image.NEAREST).point(lambda v: 255 if v > 127 else 0)
        if m.getbbox() is None:
            m = None  # nada pintado → transforma a imagem inteira
        else:
            # aumenta um pouco a área e suaviza a borda para a emenda não aparecer
            m = m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(4))
    return img, m, generated, meta


def violates_real_photo_rule(*texts):
    """Fotos enviadas podem ser de pessoas reais: nada de nudez/conteúdo sexual nelas."""
    return bool(_SEXUAL.search(_norm(" ".join(texts))))


REAL_PHOTO_MSG = ("Pedido recusado: não faço nudez ou conteúdo sexual em fotos enviadas do computador, "
                  "porque podem ser de pessoas reais. Imagens criadas aqui no gerador podem ser editadas livremente.")


def guess_category(text):
    t = _norm(text)
    if re.search(r"\b(anime|manga|cartoon|desenho animado|chibi|otaku|waifu)\b", t):
        return "anime"
    if re.search(r"\b(foto|fotografia|realista|realistic|photo|retrato real|selfie)\b", t):
        return "photo"
    return None

# ============================ GERAÇÃO ============================


def run_job(job):
    p = job["params"]
    user_prompt = p["prompt"]
    t0 = time.time()
    update(job, status="preparando", started=t0, percent=2, message="Preparando...")
    init_img, mask, from_generator, meta = job.get("inputs") or (None, None, False, {})
    mode = "inpaint" if mask is not None else "img2img" if init_img is not None else "txt2img"
    source_model = next((k for k, m in MODELS.items() if m["name"] == meta.get("model")), None)

    # 1) prompt
    prompt, category = (None, None)
    desc = None
    if p.get("enhance", True):
        if mode != "txt2img":
            # o que a imagem mostra: pelos dados salvos no PNG ou pedindo ao modelo de visão
            desc = re.sub(r",\s*(RAW photo|digital art|anime style|oil painting|3d render)\b.*$", "",
                          meta.get("prompt", ""), flags=re.I) or None
            if not desc and mode == "img2img":
                update(job, message="Analisando a imagem...")
                desc = describe_image(init_img)
            if desc:
                print(f"👁️  Imagem atual: {desc}")
        update(job, message="Traduzindo e melhorando o prompt...")
        prompt, category = enhance_prompt(user_prompt, None if mode == "txt2img" else mode, desc)
    prompt = prompt or user_prompt
    category = category or guess_category(user_prompt)
    if job["cancel"]:
        raise Cancelled()
    if violates_minor_rule(user_prompt, prompt, desc or ""):
        raise ValueError("Pedido recusado: conteúdo sexual envolvendo menores não é permitido.")
    if mode != "txt2img" and not from_generator and violates_real_photo_rule(user_prompt, prompt):
        raise ValueError(REAL_PHOTO_MSG)

    # 2) estilo e modelo
    style = p.get("style") or "auto"
    if style == "auto":
        if mode == "inpaint":
            # a área nova tem que combinar com a imagem: segue o modelo de origem (foto enviada → realista)
            style = {"realista": "foto", "anime": "anime", "arte": "arte"}.get(source_model or "realista")
        else:
            style = CATEGORY_STYLE.get(category, "nenhum")
    extra, extra_neg, preferred = STYLES.get(style, STYLES["nenhum"])
    model = p.get("model") or "auto"
    if model == "auto" or model not in MODELS:
        if mode == "inpaint":
            model = source_model or "realista"
        else:
            model = preferred or source_model or DEFAULT_MODEL
    available = engine.available()
    if not available.get(model):
        model = next((k for k, ok in available.items() if ok), None)
        if not model:
            raise RuntimeError("Nenhum modelo baixado em models/sd.")

    full_prompt = prompt + extra
    negative = ", ".join(x for x in (BASE_NEGATIVE, extra_neg, p.get("negative", "").strip()) if x)
    fast = bool(p.get("turbo"))
    steps = int(p.get("steps") or (6 if fast else 25))
    steps = max(1, min(steps, 60))
    guidance = float(p.get("guidance") or (1.5 if fast else 7.0))
    width, height = SIZES.get(p.get("size"), SIZES["quadrado"])
    strength = 1.0
    if mode != "txt2img":
        width, height = init_img.size
        strength = float(p.get("strength") or (0.85 if mode == "inpaint" else 0.6))
        strength = max(0.05, min(strength, 1.0))
        # img2img só roda (passos × força) passos; garante um mínimo para não sair borrado
        steps = min(60, max(steps, math.ceil((3 if fast else 8) / strength)))
    run_steps = steps if mode == "txt2img" else max(1, min(steps, int(steps * strength)))
    seed = p.get("seed")
    seed = int(seed) if str(seed or "").strip().lstrip("-").isdigit() else random.randint(0, 2**32 - 1)

    with engine.lock:
        if engine.key != model:
            update(job, status="carregando", percent=5, message=f"Carregando {MODELS[model]['name']}...")
        engine.load(model)
        engine.ip_off()          # antes do set_fast: trocar a LoRA com o IP-Adapter ativo quebra no 0.24
        engine.set_fast(fast)
        if job["cancel"]:
            raise Cancelled()

        verb = {"txt2img": "Gerando", "img2img": "Transformando", "inpaint": "Editando a área"}[mode]
        update(job, status="gerando", percent=8, message=f"{verb} com {MODELS[model]['name']}...")
        gen_start = time.time()

        def on_step(pipe, step, timestep, kwargs):
            if job["cancel"]:
                raise Cancelled()
            done = min(step + 1, run_steps)
            elapsed = time.time() - gen_start
            left = elapsed / done * (run_steps - done)
            update(job, percent=8 + int(90 * done / run_steps),
                   message=f"Passo {done}/{run_steps} · faltam ~{int(left)}s")
            return kwargs

        call = dict(prompt=full_prompt, negative_prompt=negative, num_inference_steps=steps,
                    guidance_scale=guidance, generator=torch.Generator("cpu").manual_seed(seed),
                    callback_on_step_end=on_step)
        if mode == "txt2img":
            call.update(width=width, height=height)
        elif mode == "img2img":
            call.update(image=init_img, strength=strength)
        else:
            call.update(image=init_img, mask_image=mask, strength=strength, width=width, height=height)
        if MODELS[model].get("clip_skip"):
            call["clip_skip"] = MODELS[model]["clip_skip"]
        print(f"🎨 [{model} {mode}{' rápido' if fast else ''}] {full_prompt}  "
              f"(seed {seed}, {run_steps} passos{f', força {strength:.2f}' if mode != 'txt2img' else ''})")
        image = engine.pipeline_for(mode)(**call).images[0]

    if mode == "inpaint":
        # fora da área pintada, mantém os pixels originais intactos
        image = Image.composite(image.resize(init_img.size), init_img, mask)

    # 3) salvar com os dados da geração dentro do PNG
    info = {"prompt": full_prompt, "negative": negative, "seed": seed, "model": MODELS[model]["name"],
            "steps": steps, "guidance": guidance, "size": f"{width}x{height}", "original": user_prompt,
            "mode": mode, "strength": strength}
    meta = PngInfo()
    meta.add_text("parameters", json.dumps(info, ensure_ascii=False))
    filename = f"image_{datetime.now():%Y%m%d_%H%M%S}_{seed}.png"
    image.save(OUTPUT_DIR / filename, pnginfo=meta)

    seconds = round(time.time() - t0)
    print(f"✅ Salvo: {filename} ({seconds}s)")
    update(job, status="concluído", percent=100, finished=time.time(), message=f"Pronta em {seconds}s",
           result={"filename": filename, "url": f"/api/image-file/{filename}", "seed": seed,
                   "prompt_used": full_prompt, "negative": negative, "model": model,
                   "model_name": MODELS[model]["name"], "style": style, "fast": fast,
                   "width": width, "height": height, "steps": run_steps, "seconds": seconds,
                   "mode": mode, "strength": strength})


def worker():
    while True:
        job_id = work_q.get()
        job = jobs.get(job_id)
        if not job or job["cancel"]:
            if job:
                update(job, status="cancelado", message="Cancelado", finished=time.time())
            continue
        try:
            kind = job["params"].get("_kind")
            if kind == "sequence":
                sequences.run_sequence(job)
            elif kind == "regenerate":
                sequences.run_regenerate(job)
            elif kind == "continue":
                sequences.run_continue(job)
            elif kind == "video":
                sequences.run_video(job)
            else:
                run_job(job)
        except Cancelled:
            update(job, status="cancelado", message="Cancelado", finished=time.time())
            print("⏹️  Geração cancelada")
        except Exception as e:
            update(job, status="erro", error=str(e), message="Erro", finished=time.time())
            print(f"❌ Erro: {e}")

# ============================ API ============================


app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "engine": "Stable Diffusion 1.5 (comunidade)",
                    "loaded": engine.key, "models": engine.available()})


@app.route("/models")
def models():
    available = engine.available()
    return jsonify({
        "models": [{"id": k, "name": m["name"], "desc": m["desc"], "available": available[k]} for k, m in MODELS.items()],
        "styles": list(STYLES), "sizes": list(SIZES), "loaded": engine.key,
    })


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return jsonify({"error": "Descreva a imagem."}), 400
    if violates_minor_rule(prompt):
        return jsonify({"error": "Pedido recusado: conteúdo sexual envolvendo menores não é permitido."}), 400
    try:
        inputs = prepare_inputs(data)   # remove as imagens em base64 do pedido
    except Exception as e:
        return jsonify({"error": f"Não consegui abrir a imagem enviada: {e}"}), 400
    if inputs[0] is not None and not inputs[2] and violates_real_photo_rule(prompt):  # foto enviada
        return jsonify({"error": REAL_PHOTO_MSG}), 400
    job_id = new_job({**data, "prompt": prompt, "has_image": inputs[0] is not None})
    jobs[job_id]["inputs"] = inputs
    work_q.put(job_id)
    return jsonify({"job_id": job_id, "queued": work_q.qsize()})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "erro", "error": "Job não encontrado", "percent": 0}), 404
    return jsonify(public(job))


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404
    update(job, cancel=True, message="Cancelando...")
    return jsonify({"ok": True})


@app.route("/jobs")
def list_jobs():
    now = time.time()
    out = []
    for j in sorted(jobs.values(), key=lambda j: j["created"], reverse=True):
        active = j["status"] not in ("concluído", "erro", "cancelado")
        if not active and now - (j["finished"] or now) > 600:
            continue
        out.append({
            "id": j["id"],
            "type": {"sequence": "Sequência", "regenerate": "Sequência", "continue": "Sequência", "video": "Vídeo narrado",
                     "plan": "Planejamento"}.get(
                j["params"].get("_kind"), "Edição" if j["params"].get("has_image") else "Imagem"),
            "prompt": j["params"]["prompt"], "status": j["status"],
            "percent": j["percent"], "message": j["message"], "active": active,
            "elapsed": int((j["finished"] or now) - (j["started"] or j["created"])),
            "model": "turbo" if j["params"].get("turbo") else (j["params"].get("model") or "auto"),
        })
    return jsonify({"jobs": out})


@app.route("/image/<path:filename>")
def image(filename):
    return send_from_directory(OUTPUT_DIR, filename)

# ---------------------------- sequências ----------------------------


@app.route("/sequence/types")
def sequence_types():
    return jsonify({"types": [{"id": k, "name": t["name"], "default": t["default"], "min": t["min"], "max": t["max"],
                               "captions": t["captions"] is not None} for k, t in sequences.TYPES.items()],
                    "ip_adapter": engine.ip_available(),
                    "voices": [{"id": k, "name": v["name"]} for k, v in narrated_video.VOICES.items()]})


@app.route("/sequence/plan", methods=["POST"])
def sequence_plan():
    """Planejamento roda fora da fila de imagens (só usa o Ollama)."""
    data = request.get_json(silent=True) or {}
    kind, topic = data.get("type"), str(data.get("topic", "")).strip()
    script = str(data.get("script", "")).strip()
    if kind not in sequences.TYPES or not (topic or script):
        return jsonify({"error": "Escolha o tipo e descreva o tema (ou cole o texto para narrar)."}), 400
    if violates_minor_rule(topic, script):
        return jsonify({"error": "Pedido recusado: conteúdo sexual envolvendo menores não é permitido."}), 400
    n = sequences.frames_count(kind, data.get("frames"))
    job_id = new_job({"_kind": "plan", "prompt": topic, "type": kind})
    job = jobs[job_id]

    def run():
        update(job, status="planejando", started=time.time(), percent=10,
               message=f"Planejando {n} quadros com a IA (pode levar 1–3 min)...")
        try:
            plan = sequences.plan_sequence(kind, topic, n, script or None)
            update(job, status="concluído", percent=100, finished=time.time(), message="Plano pronto", result={"plan": plan})
        except Exception as e:
            update(job, status="erro", error=str(e), message="Erro", finished=time.time())

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/sequence/generate", methods=["POST"])
def sequence_generate():
    data = request.get_json(silent=True) or {}
    if data.get("type") not in sequences.TYPES:
        return jsonify({"error": "Tipo de sequência inválido."}), 400
    reference = None
    if data.get("reference_image"):
        try:
            reference = decode_image(data.pop("reference_image")).convert("RGB")
        except Exception as e:
            return jsonify({"error": f"Não consegui abrir a imagem de referência: {e}"}), 400
    title = (data.get("plan") or {}).get("title") or sequences.TYPES[data["type"]]["name"]
    job_id = new_job({**data, "_kind": "sequence", "prompt": title, "has_image": reference is not None})
    jobs[job_id]["params"]["_reference"] = reference
    try:
        sequences.check_plan(data.get("plan") or {})
    except ValueError as e:
        jobs.pop(job_id, None)
        return jsonify({"error": str(e)}), 400
    work_q.put(job_id)
    return jsonify({"job_id": job_id, "queued": work_q.qsize()})


@app.route("/sequence/regenerate", methods=["POST"])
def sequence_regenerate():
    data = request.get_json(silent=True) or {}
    if not data.get("seq_id") or data.get("index") is None:
        return jsonify({"error": "seq_id e index são obrigatórios."}), 400
    job_id = new_job({**data, "_kind": "regenerate", "prompt": f"Refazer quadro {int(data['index']) + 1}"})
    work_q.put(job_id)
    return jsonify({"job_id": job_id})


@app.route("/sequence/voice-sample")
def voice_sample():
    """Amostra curta da voz escolhida (botão "Ouvir a voz")."""
    voice = request.args.get("voice", "francisca")
    try:
        rate = int(request.args.get("rate", 0))
    except ValueError:
        rate = 0
    audio, _ = narrated_video.tts("Olá! Esta é a voz que vai narrar o seu vídeo.", voice, rate)
    buf = io.BytesIO()
    narrated_video.save_wav(buf, audio)
    return app.response_class(buf.getvalue(), mimetype="audio/wav")


@app.route("/sequence/video", methods=["POST"])
def sequence_video():
    data = request.get_json(silent=True) or {}
    if not data.get("seq_id"):
        return jsonify({"error": "seq_id é obrigatório."}), 400
    if data.get("voice") and data["voice"] not in narrated_video.VOICES:
        return jsonify({"error": "Voz desconhecida."}), 400
    job_id = new_job({**data, "_kind": "video", "prompt": "Vídeo narrado"})
    work_q.put(job_id)
    return jsonify({"job_id": job_id})


@app.route("/sequence/continue", methods=["POST"])
def sequence_continue():
    data = request.get_json(silent=True) or {}
    if not data.get("seq_id"):
        return jsonify({"error": "seq_id é obrigatório."}), 400
    job_id = new_job({"seq_id": data["seq_id"], "_kind": "continue", "prompt": "Continuar sequência"})
    work_q.put(job_id)
    return jsonify({"job_id": job_id})


if __name__ == "__main__":
    print("\n🔥 ARMAGEDON — Gerador de Imagens (sem filtro de conteúdo)")
    print("=" * 60)
    for key, ok in engine.available().items():
        print(f"  {'✅' if ok else '❌'} {key:9s} {MODELS[key]['name']}")
    print(f"  CPU: {CPU_THREADS} threads · imagens em {OUTPUT_DIR}")
    threading.Thread(target=worker, daemon=True).start()

    # pré-carrega o modelo padrão para a primeira imagem sair mais rápido
    def preload():
        with engine.lock:
            if engine.available().get(DEFAULT_MODEL):
                engine.load(DEFAULT_MODEL)
    threading.Thread(target=preload, daemon=True).start()

    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
