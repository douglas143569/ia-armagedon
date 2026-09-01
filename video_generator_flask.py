#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Vídeos/GIFs

Flask + progresso + cancelamento + SD-Turbo + 3 modos de geração.

Endpoints:
  POST /generate  {prompt, duration, fps, turbo?, mode?, size?, steps?}  -> {job_id}
  GET  /status/<job_id>   |   GET /jobs   |   POST /cancel/<job_id>   |   GET /health

Modos (mode):
  frames    (padrão) : N imagens independentes por txt2img       (mais lento, conteúdo varia)
  camera             : 1 imagem + zoom/pan (Ken Burns)           (mais rápido, movimento de câmera)
  evolucao           : img2img encadeado a partir do frame anterior (médio, animação que evolui)

Modelos (turbo=true -> SD-Turbo, 4 steps, guidance 0). Só um modelo na RAM por vez.
Geração serializada: 1 job por vez (fila).
"""
import os, sys, gc, threading, time, uuid
from datetime import datetime
from flask import Flask, request, jsonify
from PIL import Image
import torch
from diffusers import StableDiffusionPipeline, AutoPipelineForImage2Image

app = Flask(__name__)
VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "videos_generated")
os.makedirs(VIDEOS_DIR, exist_ok=True)

MODELS = {
    "sd15":  {"repo": "runwayml/stable-diffusion-v1-5", "steps": 15, "guidance": 7.5},
    "turbo": {"repo": "stabilityai/sd-turbo",           "steps": 4,  "guidance": 0.0},
}

IDLE_UNLOAD_SEC = int(os.environ.get("SD_IDLE_UNLOAD_SEC", "600"))  # solta o modelo da RAM após 10 min ocioso

jobs = {}
jobs_lock = threading.Lock()
gen_lock = threading.Lock()
_pipe_state = {"key": None, "pipe": None, "i2i": None, "last_used": time.time()}


def get_pipe(key):
    _pipe_state["last_used"] = time.time()
    if _pipe_state["key"] == key and _pipe_state["pipe"] is not None:
        return _pipe_state["pipe"]
    if _pipe_state["pipe"] is not None:
        _pipe_state.update(pipe=None, i2i=None, key=None)
        gc.collect()
    cfg = MODELS[key]
    print(f"Carregando modelo '{key}' ({cfg['repo']})...")
    sys.stdout.flush()
    p = StableDiffusionPipeline.from_pretrained(
        cfg["repo"], torch_dtype=torch.float32, safety_checker=None
    ).to("cpu")
    p.enable_attention_slicing()
    _pipe_state.update(pipe=p, i2i=None, key=key, last_used=time.time())
    print(f"Modelo '{key}' pronto.")
    sys.stdout.flush()
    return p


def _idle_watchdog():
    """Descarrega o Stable Diffusion da RAM quando ficar IDLE_UNLOAD_SEC sem uso."""
    while True:
        time.sleep(60)
        if _pipe_state["pipe"] is None:
            continue
        if gen_lock.locked():
            _pipe_state["last_used"] = time.time()
            continue
        ocioso = time.time() - _pipe_state["last_used"]
        if ocioso >= IDLE_UNLOAD_SEC:
            print(f"[idle {int(ocioso)}s] descarregando modelo '{_pipe_state['key']}' da RAM")
            _pipe_state.update(pipe=None, i2i=None, key=None)
            gc.collect()
            sys.stdout.flush()


def get_i2i():
    """Pipeline img2img reaproveitando os pesos já carregados (sem custo de RAM extra)."""
    if _pipe_state["i2i"] is None:
        _pipe_state["i2i"] = AutoPipelineForImage2Image.from_pipe(_pipe_state["pipe"])
    return _pipe_state["i2i"]


def _prune_old_jobs():
    done = [j for j in jobs.values() if j["status"] in ("concluído", "erro", "cancelado")]
    if len(done) > 30:
        done.sort(key=lambda j: j["created"])
        for j in done[:-30]:
            jobs.pop(j["id"], None)


def ken_burns_frames(base, n, out_size):
    """Gera n frames aplicando zoom-in + pan suave sobre a imagem base."""
    W, H = base.size
    frames = []
    for i in range(n):
        t = i / max(1, n - 1)
        zoom = 1.0 + 0.28 * t
        cw, ch = int(W / zoom), int(H / zoom)
        x = int((W - cw) * (0.15 + 0.70 * t))
        y = int((H - ch) * (0.10 + 0.55 * t))
        frame = base.crop((x, y, x + cw, y + ch)).resize((out_size, out_size), Image.LANCZOS)
        frames.append(frame)
    return frames


def generate_video(job_id, prompt, duration, fps, model_key, mode, size, steps):
    job = jobs[job_id]
    try:
        cfg = MODELS[model_key]
        base_steps = steps or cfg["steps"]
        guidance = cfg["guidance"]
        frames = []

        def on_step(pipe_ref, step, timestep, cb_kwargs):
            if job.get("cancel"):
                pipe_ref._interrupt = True
            return cb_kwargs

        job["message"] = "Na fila..."
        with gen_lock:
            if job.get("cancel"):
                job.update(status="cancelado", message="Cancelado pelo usuário",
                           result={"success": False, "error": "cancelado"})
                return
            job.update(status="gerando", message=f"Carregando modelo {model_key}...")
            pipe = get_pipe(model_key)

            if mode == "camera":
                num_frames = max(4, duration * fps)
                job.update(total=num_frames, message="Gerando imagem base...")
                pipe._interrupt = False
                with torch.no_grad():
                    base = pipe(prompt, height=size, width=size,
                               num_inference_steps=base_steps, guidance_scale=guidance,
                               callback_on_step_end=on_step).images[0]
                if job.get("cancel"):
                    raise RuntimeError("cancelado")
                job.update(percent=60, message="Aplicando movimento de câmera...")
                frames = ken_burns_frames(base, num_frames, size)
                job["percent"] = 95

            elif mode == "evolucao":
                num_frames = max(2, duration * fps // 2)
                job.update(total=num_frames)
                i2i = get_i2i()
                prev = None
                for i in range(num_frames):
                    if job.get("cancel"):
                        break
                    job.update(current=i + 1, percent=int(i / num_frames * 100),
                               message=f"Frame {i + 1}/{num_frames}")
                    pipe._interrupt = False
                    with torch.no_grad():
                        if prev is None:
                            img = pipe(prompt, height=size, width=size,
                                       num_inference_steps=base_steps, guidance_scale=guidance,
                                       callback_on_step_end=on_step).images[0]
                        else:
                            img = i2i(prompt=prompt, image=prev, strength=0.45,
                                      num_inference_steps=max(2, base_steps),
                                      guidance_scale=guidance,
                                      callback_on_step_end=on_step).images[0]
                    if job.get("cancel"):
                        break
                    frames.append(img)
                    prev = img

            else:  # "frames"
                num_frames = max(2, duration * fps // 2)
                job.update(total=num_frames)
                for i in range(num_frames):
                    if job.get("cancel"):
                        break
                    job.update(current=i + 1, percent=int(i / num_frames * 100),
                               message=f"Frame {i + 1}/{num_frames}")
                    pipe._interrupt = False
                    with torch.no_grad():
                        img = pipe(prompt, height=size, width=size,
                                   num_inference_steps=base_steps, guidance_scale=guidance,
                                   callback_on_step_end=on_step).images[0]
                    if job.get("cancel"):
                        break
                    frames.append(img)

        if job.get("cancel") or not frames:
            job.update(status="cancelado", message="Cancelado pelo usuário",
                       result={"success": False, "error": "cancelado"})
            print(f"Job {job_id} cancelado\n")
            return

        job["message"] = "Salvando GIF..."
        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.gif"
        filepath = os.path.join(VIDEOS_DIR, filename)
        frames[0].save(filepath, save_all=True, append_images=frames[1:],
                       duration=int(1000 / fps), loop=0)
        _pipe_state["last_used"] = time.time()
        job.update(status="concluído", percent=100, message="Concluído!",
                   filename=filename, result={"success": True, "filename": filename})
        print(f"Job {job_id} salvo: {filepath} ({len(frames)} frames, modo {mode})\n")

    except Exception as e:
        if job.get("cancel") or str(e) == "cancelado":
            job.update(status="cancelado", message="Cancelado pelo usuário",
                       result={"success": False, "error": "cancelado"})
        else:
            job.update(status="erro", message=str(e),
                       result={"success": False, "error": str(e)})
            print(f"Job {job_id} erro: {e}\n")


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(silent=True) or {}
        prompt = (data.get("prompt") or "landscape").strip()
        duration = max(1, int(data.get("duration", 4)))
        fps = max(1, int(data.get("fps", 6)))
        model_key = "turbo" if data.get("turbo") else "sd15"
        mode = data.get("mode") if data.get("mode") in ("frames", "camera", "evolucao") else "frames"
        size = 384 if int(data.get("size", 512)) <= 384 else 512
        steps = data.get("steps")
        steps = max(1, min(30, int(steps))) if steps else None

        job_id = str(uuid.uuid4())[:8]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id, "type": "vídeo", "prompt": prompt, "model": model_key,
                "mode": mode, "size": size,
                "status": "na fila", "current": 0, "total": 0, "percent": 0,
                "message": "Na fila", "created": time.time(),
                "cancel": False, "result": None,
            }
            _prune_old_jobs()
        threading.Thread(target=generate_video,
                         args=(job_id, prompt, duration, fps, model_key, mode, size, steps),
                         daemon=True).start()
        return jsonify({"job_id": job_id}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404
    resp = {
        "status": job["status"], "percent": job["percent"],
        "current": job["current"], "total": job["total"],
        "message": job["message"], "prompt": job["prompt"],
        "type": job["type"], "model": job.get("model"), "mode": job.get("mode"),
    }
    if job["status"] == "concluído":
        resp["result"] = job["result"]
    elif job["status"] in ("erro", "cancelado"):
        resp["error"] = job["message"]
    return jsonify(resp), 200


@app.route("/jobs", methods=["GET"])
def list_jobs():
    now = time.time()
    out = [{
        "id": j["id"], "type": j["type"], "prompt": j["prompt"], "model": j.get("model"),
        "mode": j.get("mode"),
        "status": j["status"], "percent": j["percent"], "message": j["message"],
        "elapsed": int(now - j["created"]),
        "active": j["status"] in ("na fila", "gerando"),
    } for j in sorted(jobs.values(), key=lambda x: x["created"], reverse=True)]
    return jsonify({"jobs": out}), 200


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404
    job["cancel"] = True
    if job["status"] == "na fila":
        job.update(status="cancelado", message="Cancelado pelo usuário")
    return jsonify({"ok": True}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": _pipe_state["key"],
                    "carregado": _pipe_state["pipe"] is not None,
                    "ocioso_s": int(time.time() - _pipe_state["last_used"])}), 200


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Gerador de Videos/GIFs (SD-1.5 + SD-Turbo, 3 modos)")
    print("=" * 50)
    print(f"modelo carrega sob demanda; solta da RAM após {IDLE_UNLOAD_SEC}s ocioso")
    threading.Thread(target=_idle_watchdog, daemon=True).start()
    print("http://localhost:5001\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5001, debug=False, threaded=True)
