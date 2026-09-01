#!/usr/bin/env python3
"""ARMAGEDON - servidor de vídeo em GPU (porta 5001).

Mesma API do gerador local (video_generator_flask.py), então o hub do ARMAGEDON
fala com ele sem mudança — basta apontar o hub pra esta máquina (ver README-GPU.md).

  POST /generate  {prompt, duration}   -> {job_id}     (duration = segundos-alvo do vídeo)
  GET  /status/<job_id>   |   GET /jobs   |   POST /cancel/<job_id>   |   GET /health
"""
import os, sys, threading, time, uuid
from flask import Flask, request, jsonify
import pipeline

app = Flask(__name__)
jobs = {}
jobs_lock = threading.Lock()
gen_lock = threading.Lock()


def _run(job_id, prompt, target_seconds, start_image):
    job = jobs[job_id]
    try:
        job["message"] = "Na fila..."
        with gen_lock:
            if job.get("cancel"):
                job.update(status="cancelado", message="Cancelado"); return
            job.update(status="gerando", message="Iniciando...")

            def prog(msg, frac):
                job["message"] = msg
                job["percent"] = int(frac * 100)

            out = pipeline.generate(prompt, target_seconds, start_image=start_image,
                                    progress_cb=prog, cancel_cb=lambda: job.get("cancel"))
        if job.get("cancel") or not out:
            job.update(status="cancelado", message="Cancelado",
                       result={"success": False, "error": "cancelado"})
            return
        fname = os.path.basename(out)
        job.update(status="concluído", percent=100, message="Concluído!",
                   filename=fname, result={"success": True, "filename": fname, "path": out})
        print(f"Job {job_id}: {out}", flush=True)
    except Exception as e:
        job.update(status="erro", message=str(e),
                   result={"success": False, "error": str(e)})
        print(f"Job {job_id} erro: {e}", flush=True)


@app.route("/generate", methods=["POST"])
def generate():
    d = request.get_json(silent=True) or {}
    prompt = (d.get("prompt") or "a landscape").strip()
    target = int(d.get("duration") or d.get("target_seconds") or 0) or None
    start_image = d.get("start_image")
    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[job_id] = {"id": job_id, "type": "vídeo", "prompt": prompt,
                        "status": "na fila", "percent": 0, "current": 0, "total": 0,
                        "message": "Na fila", "created": time.time(),
                        "cancel": False, "result": None}
    threading.Thread(target=_run, args=(job_id, prompt, target, start_image), daemon=True).start()
    return jsonify({"job_id": job_id}), 200


@app.route("/status/<job_id>")
def status(job_id):
    j = jobs.get(job_id)
    if not j:
        return jsonify({"error": "Job não encontrado"}), 404
    r = {k: j[k] for k in ("status", "percent", "current", "total", "message", "prompt", "type")}
    if j["status"] == "concluído":
        r["result"] = j["result"]
    elif j["status"] in ("erro", "cancelado"):
        r["error"] = j["message"]
    return jsonify(r)


@app.route("/jobs")
def list_jobs():
    now = time.time()
    return jsonify({"jobs": [{
        "id": j["id"], "type": j["type"], "prompt": j["prompt"],
        "status": j["status"], "percent": j["percent"], "message": j["message"],
        "elapsed": int(now - j["created"]),
        "active": j["status"] in ("na fila", "gerando"),
    } for j in sorted(jobs.values(), key=lambda x: x["created"], reverse=True)]})


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel(job_id):
    j = jobs.get(job_id)
    if not j:
        return jsonify({"error": "Job não encontrado"}), 404
    j["cancel"] = True
    if j["status"] == "na fila":
        j.update(status="cancelado", message="Cancelado")
    return jsonify({"ok": True})


@app.route("/health")
def health():
    cfg = pipeline.load_config()
    return jsonify({"status": "ok", "preset": cfg["preset"],
                    "repo": cfg["_preset"]["repo"], "target_seconds": cfg["target_seconds"]})


if __name__ == "__main__":
    print("ARMAGEDON gerador de vídeo (GPU) — http://0.0.0.0:5001", flush=True)
    app.run(host="0.0.0.0", port=5001, threaded=True)
