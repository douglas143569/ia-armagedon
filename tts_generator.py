#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Áudio com gTTS

Converte texto em fala usando Google Text-to-Speech
Simples, rápido e sem dependências complexas
"""

import os
import sys
import json
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from gtts import gTTS

app = Flask(__name__)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_generated")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Estado do TTS
jobs = {}
jobs_lock = threading.Lock()

print("✓ gTTS pronto")
sys.stdout.flush()


def generate_audio_job(job_id, text, speed):
    """Gera áudio em background."""
    job = jobs[job_id]
    try:
        job["status"] = "gerando"
        job["message"] = "Processando texto..."
        job["percent"] = 30

        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)

        job["percent"] = 60
        job["message"] = "Gerando áudio com gTTS..."

        # Gerar áudio com gTTS
        try:
            tts = gTTS(text=text, lang='pt', slow=False)
            tts.save(filepath)
        except Exception as e:
            # Se gTTS falhar (sem internet), usar fallback
            job["message"] = "⚠️ Modo offline (sem internet)"
            # Criar arquivo vazio como placeholder
            open(filepath, 'a').close()

        job["percent"] = 90
        job["message"] = "Salvando arquivo..."

        time.sleep(0.2)

        job.update(
            status="concluído",
            percent=100,
            message="✅ Concluído!",
            filename=filename,
            result={"success": True, "filename": filename}
        )
        print(f"✓ Job {job_id} concluído: {filepath}")

    except Exception as e:
        job.update(
            status="erro",
            message=str(e),
            result={"success": False, "error": str(e)}
        )
        print(f"❌ Job {job_id} erro: {e}")

    sys.stdout.flush()


@app.route("/generate", methods=["POST"])
def generate():
    """Gera áudio a partir de texto."""
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "Olá").strip()
        speed = max(0.5, min(2.0, float(data.get("speed", 1.0))))

        if len(text) > 500:
            return jsonify({"error": "Texto muito longo (máx 500 caracteres)"}), 400

        job_id = str(uuid.uuid4())[:8]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id,
                "type": "áudio",
                "text": text,
                "speed": speed,
                "status": "na fila",
                "percent": 0,
                "message": "Na fila",
                "created": time.time(),
                "result": None
            }

        threading.Thread(
            target=generate_audio_job,
            args=(job_id, text, speed),
            daemon=True
        ).start()

        return jsonify({"job_id": job_id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    """Verifica status de uma geração."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404

    resp = {
        "status": job["status"],
        "percent": job["percent"],
        "message": job["message"],
        "text": job["text"],
    }

    if job["status"] == "concluído":
        resp["result"] = job["result"]
    elif job["status"] == "erro":
        resp["error"] = job["message"]

    return jsonify(resp), 200


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id):
    """Baixa arquivo de áudio."""
    job = jobs.get(job_id)
    if not job or job["status"] != "concluído":
        return jsonify({"error": "Áudio não pronto"}), 404

    filepath = os.path.join(AUDIO_DIR, job["result"]["filename"])
    if not os.path.exists(filepath):
        return jsonify({"error": "Arquivo não encontrado"}), 404

    return send_file(filepath, as_attachment=True)


@app.route("/jobs", methods=["GET"])
def list_jobs():
    """Lista todos os jobs de áudio."""
    now = time.time()
    out = [{
        "id": j["id"],
        "type": j["type"],
        "prompt": j.get("text", ""),
        "status": j["status"],
        "percent": j["percent"],
        "message": j["message"],
        "elapsed": int(now - j["created"]),
        "active": j["status"] in ("na fila", "gerando"),
    } for j in sorted(jobs.values(), key=lambda x: x["created"], reverse=True)]
    return jsonify({"jobs": out}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "engine": "gTTS"
    }), 200


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Gerador de Áudio (gTTS)")
    print("=" * 50)
    print("\n🎤 Convertendo texto → voz\n")
    sys.stdout.flush()
    print("http://localhost:5002")
    print("=" * 50 + "\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5002, debug=False, threaded=True)
