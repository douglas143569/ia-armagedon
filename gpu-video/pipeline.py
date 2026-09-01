#!/usr/bin/env python3
"""ARMAGEDON - pipeline de vídeo em GPU (diffusers).

Gera clipes curtos com um modelo de vídeo aberto e emenda até chegar em
`target_seconds`, encadeando cada clipe a partir do último frame do anterior.

CLI (teste sem servidor):
    python pipeline.py --prompt "a neon city at night, rain" --target-seconds 20 --out saida.mp4

Config em config.yaml. Modelos/VRAM em models.md.

OBS: escrito sem GPU pra testar. Na 1ª execução no pod, o ponto provável de
ajuste é `build_pipe()` (assinatura de pipeline muda entre versões do diffusers).
"""
import os, sys, gc, time, math, argparse, subprocess, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.yaml")
OUT_DIR = os.path.join(HERE, "videos_out")
os.makedirs(OUT_DIR, exist_ok=True)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    p = cfg["presets"][cfg["preset"]]
    cfg["_preset"] = p
    return cfg


# ---------------------------------------------------------------------------
# Construção do pipeline por tipo de modelo
# ---------------------------------------------------------------------------
def _dtype(name):
    import torch
    return {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[name]


def build_pipe(preset, want_i2v):
    """Retorna (pipe, is_i2v). want_i2v=True pede o pipeline image-to-video."""
    import torch
    kind, repo, dt = preset["kind"], preset["repo"], _dtype(preset["dtype"])

    if kind == "ltx":
        from diffusers import LTXPipeline, LTXImageToVideoPipeline
        cls = LTXImageToVideoPipeline if want_i2v else LTXPipeline
        pipe = cls.from_pretrained(repo, torch_dtype=dt)

    elif kind == "cogvideox":
        from diffusers import CogVideoXImageToVideoPipeline, CogVideoXPipeline
        # o repo do preset é I2V; pra clipe 0 sem imagem, usa-se semente SDXL-Turbo (ver generate())
        cls = CogVideoXImageToVideoPipeline if want_i2v else CogVideoXPipeline
        pipe = cls.from_pretrained(repo, torch_dtype=dt)

    elif kind == "wan":
        from diffusers import WanImageToVideoPipeline, WanPipeline, AutoencoderKLWan
        vae = AutoencoderKLWan.from_pretrained(repo, subfolder="vae", torch_dtype=torch.float32)
        cls = WanImageToVideoPipeline if want_i2v else WanPipeline
        pipe = cls.from_pretrained(repo, vae=vae, torch_dtype=dt)

    elif kind == "hunyuan":
        from diffusers import HunyuanVideoImageToVideoPipeline, HunyuanVideoPipeline
        cls = HunyuanVideoImageToVideoPipeline if want_i2v else HunyuanVideoPipeline
        pipe = cls.from_pretrained(repo, torch_dtype=dt)

    else:
        raise ValueError(f"kind desconhecido: {kind}")

    if preset.get("offload"):
        pipe.enable_model_cpu_offload()
    else:
        pipe = pipe.to("cuda")
    try:
        pipe.vae.enable_tiling()
    except Exception:
        pass
    return pipe, want_i2v


def preload():
    """Baixa os pesos do preset atual (chamado pelo setup.sh)."""
    cfg = load_config()
    print(f"preload: {cfg['_preset']['repo']}")
    build_pipe(cfg["_preset"], want_i2v=False if cfg["_preset"]["kind"] != "cogvideox" else True)
    print("ok")


# ---------------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------------
def _seed_image(prompt, w, h):
    """Frame inicial via SDXL-Turbo (rápido) quando o modelo é só I2V e não há --start-image."""
    import torch
    from diffusers import AutoPipelineForText2Image
    sd = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sdxl-turbo", torch_dtype=torch.float16).to("cuda")
    img = sd(prompt=prompt, num_inference_steps=2, guidance_scale=0.0,
             width=w, height=h).images[0]
    del sd; gc.collect(); torch.cuda.empty_cache()
    return img


def _gen_clip(pipe, is_i2v, preset, prompt, num_frames, image, generator):
    kw = dict(prompt=prompt, width=preset["width"], height=preset["height"],
              num_frames=num_frames, num_inference_steps=preset["steps"],
              guidance_scale=preset["guidance"], generator=generator)
    if is_i2v:
        kw["image"] = image
    out = pipe(**kw)
    return out.frames[0]   # lista de PIL.Image


def generate(prompt, target_seconds=None, out_path=None, start_image=None,
             progress_cb=None, cancel_cb=None):
    import torch
    from diffusers.utils import export_to_video
    from PIL import Image

    cfg = load_config()
    p = cfg["_preset"]
    target_seconds = target_seconds or cfg["target_seconds"]
    per_clip = cfg["per_clip_seconds"]
    model_fps = p["model_fps"]
    n_clips = max(1, math.ceil(target_seconds / per_clip))
    frames_per_clip = per_clip * model_fps + 1
    chain = cfg["chain_mode"] == "last_frame"
    seed = cfg["seed"]
    gen = torch.Generator("cuda")
    if seed >= 0:
        gen = gen.manual_seed(seed)

    def prog(msg, frac):
        print(f"  {msg}", flush=True)
        if progress_cb:
            progress_cb(msg, frac)

    # pipeline t2v pra clipe 0 (se o modelo tiver), i2v pros seguintes
    kind = p["kind"]
    has_t2v = kind in ("ltx", "wan", "hunyuan")
    all_frames = []
    img = Image.open(start_image).convert("RGB").resize((p["width"], p["height"])) if start_image else None

    for i in range(n_clips):
        if cancel_cb and cancel_cb():
            prog("cancelado", 0); return None
        prog(f"clipe {i+1}/{n_clips}", i / n_clips)

        want_i2v = (i > 0 and chain) or (not has_t2v) or (img is not None and i == 0)
        if want_i2v and img is None:
            img = _seed_image(prompt, p["width"], p["height"])
        pipe, is_i2v = build_pipe(p, want_i2v=want_i2v)
        frames = _gen_clip(pipe, is_i2v, p, prompt, frames_per_clip, img, gen)
        del pipe; gc.collect(); torch.cuda.empty_cache()

        if i > 0:
            frames = frames[1:]            # descarta seam (≈ último frame do clipe anterior)
        all_frames.extend(frames)
        if chain and frames:
            img = frames[-1]

    prog("montando mp4", 0.9)
    out_path = out_path or os.path.join(OUT_DIR, f"armagedon_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
    raw = out_path.replace(".mp4", "_raw.mp4")
    export_to_video(all_frames, raw, fps=model_fps)
    _postprocess(raw, out_path, cfg)
    prog("concluído", 1.0)
    return out_path


def _postprocess(raw, final, cfg):
    """Interpolação p/ fps_final, upscale e áudio — tudo opcional, via ffmpeg."""
    p = cfg["_preset"]
    steps = []
    vf = []
    if cfg.get("interpolate") and cfg["fps_final"] > p["model_fps"]:
        vf.append(f"minterpolate=fps={cfg['fps_final']}:mi_mode=mci:mc_mode=aobmc:vsbmc=1")
    cmd = ["ffmpeg", "-y", "-i", raw]
    aud = cfg.get("audio", "none")
    if isinstance(aud, str) and aud.startswith("file:"):
        cmd += ["-i", aud[5:], "-shortest", "-c:a", "aac"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", final]
    subprocess.run(cmd, check=True)
    try:
        os.remove(raw)
    except OSError:
        pass
    if cfg.get("upscale"):
        try:
            up = final.replace(".mp4", "_2x.mp4")
            subprocess.run(["realesrgan-ncnn-vulkan", "-i", final, "-o", up, "-s", "2"], check=True)
            os.replace(up, final)
        except Exception as e:
            print(f"(upscale pulado: {e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--target-seconds", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--start-image", default=None)
    a = ap.parse_args()
    path = generate(a.prompt, a.target_seconds, a.out, a.start_image)
    print("SAÍDA:", path)


if __name__ == "__main__":
    main()
