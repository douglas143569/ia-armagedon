#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Imagens (Flask + jobs + cancelamento + SD-Turbo)

Endpoints:
  POST /generate        {prompt, turbo?}    -> {job_id}         (assíncrono, entra na fila)
  GET  /status/<job_id>                     -> estado de 1 job
  GET  /jobs                                -> lista todos os jobs
  POST /cancel/<job_id>                     -> marca job para cancelar
  GET  /health                              -> {status, model}

Modelos:
  sd15  (padrão) : Stable Diffusion 1.5 - 20 steps, guidance 7.5
  turbo          : SD-Turbo - 4 steps, guidance 0.0  (~4x mais rápido)
Só um modelo fica na RAM por vez; trocar de modelo recarrega (leva 1-2 min,
e o Turbo baixa ~5 GB na primeira vez).
"""
import os, sys, gc, threading, uuid, time
from datetime import datetime
from flask import Flask, request, jsonify
import torch
from diffusers import StableDiffusionPipeline

app = Flask(__name__)
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images_generated")
os.makedirs(IMAGES_DIR, exist_ok=True)

MODELS = {
    "sd15":  {"repo": "runwayml/stable-diffusion-v1-5", "steps": 20, "guidance": 7.5},
    "turbo": {"repo": "stabilityai/sd-turbo",           "steps": 4,  "guidance": 0.0},
}

IDLE_UNLOAD_SEC = int(os.environ.get("SD_IDLE_UNLOAD_SEC", "600"))  # solta o modelo da RAM após 10 min ocioso

jobs = {}
jobs_lock = threading.Lock()      # protege o dict jobs
gen_lock = threading.Lock()       # serializa geração: 1 por vez (é a "fila")
_pipe_state = {"key": None, "pipe": None, "last_used": time.time()}


def get_pipe(key):
    """Retorna o pipeline do modelo pedido, recarregando se for outro (ou se foi descarregado)."""
    _pipe_state["last_used"] = time.time()
    if _pipe_state["key"] == key and _pipe_state["pipe"] is not None:
        return _pipe_state["pipe"]
    if _pipe_state["pipe"] is not None:
        _pipe_state["pipe"] = None
        _pipe_state["key"] = None
        gc.collect()
    cfg = MODELS[key]
    print(f"Carregando modelo '{key}' ({cfg['repo']})...")
    sys.stdout.flush()
    p = StableDiffusionPipeline.from_pretrained(
        cfg["repo"], torch_dtype=torch.float32, safety_checker=None
    )
    p = p.to("cpu")
    p.enable_attention_slicing()
    _pipe_state["pipe"] = p
    _pipe_state["key"] = key
    _pipe_state["last_used"] = time.time()
    print(f"Modelo '{key}' pronto.")
    sys.stdout.flush()
    return p


def _idle_watchdog():
    """Descarrega o Stable Diffusion da RAM quando ficar IDLE_UNLOAD_SEC sem uso."""
    while True:
        time.sleep(60)
        if _pipe_state["pipe"] is None:
            continue
        if gen_lock.locked():                    # tem geração rodando
            _pipe_state["last_used"] = time.time()
            continue
        ocioso = time.time() - _pipe_state["last_used"]
        if ocioso >= IDLE_UNLOAD_SEC:
            print(f"[idle {int(ocioso)}s] descarregando modelo '{_pipe_state['key']}' da RAM")
            _pipe_state["pipe"] = None
            _pipe_state["key"] = None
            gc.collect()
            sys.stdout.flush()


def _prune_old_jobs():
    done = [j for j in jobs.values() if j["status"] in ("concluído", "erro", "cancelado")]
    if len(done) > 30:
        done.sort(key=lambda j: j["created"])
        for j in done[:-30]:
            jobs.pop(j["id"], None)


def run_job(job_id, prompt, model_key):
    job = jobs[job_id]
    try:
        cfg = MODELS[model_key]
        job["message"] = "Na fila..."
        with gen_lock:
            if job.get("cancel"):
                job["status"] = "cancelado"; job["message"] = "Cancelado pelo usuário"; return
            job["status"] = "gerando"
            job["message"] = f"Carregando modelo {model_key}..."
            pipe = get_pipe(model_key)
            steps = cfg["steps"]
            job["message"] = "Gerando..."

            def on_step(pipe_ref, step, timestep, cb_kwargs):
                if job.get("cancel"):
                    pipe_ref._interrupt = True
                else:
                    job["percent"] = int((step + 1) / steps * 100)
                    job["message"] = f"Step {step + 1}/{steps}"
                return cb_kwargs

            pipe._interrupt = False
            with torch.no_grad():
                out = pipe(
                    prompt, height=512, width=512,
                    num_inference_steps=steps, guidance_scale=cfg["guidance"],
                    callback_on_step_end=on_step,
                )

        if job.get("cancel"):
            job["status"] = "cancelado"; job["message"] = "Cancelado pelo usuário"
            print(f"Job {job_id} cancelado\n"); return

        image = out.images[0]
        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.png"
        image.save(os.path.join(IMAGES_DIR, filename))
        _pipe_state["last_used"] = time.time()
        job.update(status="concluído", percent=100, message="Concluído!",
                   result={"success": True, "filename": filename})
        print(f"Job {job_id} salvo: {filename}\n")

    except Exception as e:
        if job.get("cancel"):
            job["status"] = "cancelado"; job["message"] = "Cancelado pelo usuário"
        else:
            job.update(status="erro", message=str(e),
                       result={"success": False, "error": str(e)})
            print(f"Job {job_id} erro: {e}\n")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "landscape").strip()
    model_key = "turbo" if data.get("turbo") else "sd15"
    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id, "type": "imagem", "prompt": prompt, "model": model_key,
            "status": "na fila", "percent": 0, "message": "Na fila",
            "created": time.time(), "cancel": False, "result": None,
        }
        _prune_old_jobs()
    threading.Thread(target=run_job, args=(job_id, prompt, model_key), daemon=True).start()
    return jsonify({"job_id": job_id}), 200


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404
    resp = {k: job[k] for k in ("status", "percent", "message", "prompt", "type", "model")}
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
    if job["status"] in ("na fila",):
        job["status"] = "cancelado"; job["message"] = "Cancelado pelo usuário"
    return jsonify({"ok": True}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": _pipe_state["key"],
                    "carregado": _pipe_state["pipe"] is not None,
                    "ocioso_s": int(time.time() - _pipe_state["last_used"])}), 200


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Gerador de Imagens (SD-1.5 + SD-Turbo)")
    print("=" * 50)
    print(f"modelo carrega sob demanda; solta da RAM após {IDLE_UNLOAD_SEC}s ocioso")
    threading.Thread(target=_idle_watchdog, daemon=True).start()
    print("http://localhost:5000\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5000, debug=False, threaded=True)
