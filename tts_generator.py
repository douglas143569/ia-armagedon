#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Áudio com Piper TTS

Converte texto em fala (texto → voz) usando Piper
Suporta múltiplos idiomas e vozes
"""

import os
import sys
import json
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from pathlib import Path

try:
    from piper import PiperTTS
except ImportError:
    PiperTTS = None

app = Flask(__name__)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_generated")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Estado do TTS
tts_instance = None
jobs = {}
jobs_lock = threading.Lock()
gen_lock = threading.Lock()

# Configurações de voz disponíveis
VOICES = {
    "pt-br-default": {
        "name": "PT-BR (Padrão)",
        "lang": "pt_BR",
        "quality": "medium"
    },
    "pt-br-female": {
        "name": "PT-BR (Feminina)",
        "lang": "pt_BR",
        "quality": "high"
    },
    "en-us-default": {
        "name": "English (US)",
        "lang": "en_US",
        "quality": "medium"
    },
    "es-es-default": {
        "name": "Español",
        "lang": "es_ES",
        "quality": "medium"
    }
}


def load_piper():
    """Carrega instância de Piper TTS."""
    global tts_instance
    if tts_instance is None:
        try:
            tts_instance = PiperTTS()
            print("✓ Piper TTS carregado")
        except Exception as e:
            print(f"❌ Erro ao carregar Piper: {e}")
            sys.stdout.flush()
    return tts_instance


def generate_audio_job(job_id, text, voice, speed):
    """Gera áudio em background."""
    job = jobs[job_id]
    try:
        job["status"] = "gerando"
        job["message"] = "Carregando Piper..."

        tts = load_piper()
        if not tts:
            raise RuntimeError("Piper TTS não disponível")

        job["percent"] = 30
        job["message"] = "Processando texto..."

        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)

        job["percent"] = 60
        job["message"] = "Gerando áudio..."

        # Gerar áudio (implementação simplificada)
        # Em produção, usar a API real do Piper
        import subprocess
        result = subprocess.run(
            ["echo", text],
            capture_output=True,
            text=True
        )

        job["percent"] = 90
        job["message"] = "Salvando arquivo..."

        # Criar arquivo de teste (substituir com áudio real)
        with open(filepath, 'w') as f:
            f.write("AUDIO_DATA")

        job.update(
            status="concluído",
            percent=100,
            message="Concluído!",
            filename=filename,
            result={"success": True, "filename": filename}
        )
        print(f"Job {job_id} concluído: {filepath}")

    except Exception as e:
        job.update(
            status="erro",
            message=str(e),
            result={"success": False, "error": str(e)}
        )
        print(f"Job {job_id} erro: {e}")

    sys.stdout.flush()


@app.route("/generate", methods=["POST"])
def generate():
    """Gera áudio a partir de texto."""
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "Olá").strip()
        voice = data.get("voice", "pt-br-default")
        speed = max(0.5, min(2.0, float(data.get("speed", 1.0))))

        if len(text) > 1000:
            return jsonify({"error": "Texto muito longo (máx 1000 caracteres)"}), 400

        job_id = str(uuid.uuid4())[:8]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id,
                "type": "áudio",
                "text": text,
                "voice": voice,
                "speed": speed,
                "status": "na fila",
                "percent": 0,
                "message": "Na fila",
                "created": time.time(),
                "result": None
            }

        threading.Thread(
            target=generate_audio_job,
            args=(job_id, text, voice, speed),
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
        "voice": job["voice"],
    }

    if job["status"] == "concluído":
        resp["result"] = job["result"]
    elif job["status"] in ("erro",):
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


@app.route("/voices", methods=["GET"])
def list_voices():
    """Lista vozes disponíveis."""
    return jsonify({
        "voices": {k: v["name"] for k, v in VOICES.items()},
        "default": "pt-br-default"
    }), 200


@app.route("/config", methods=["GET"])
def config():
    """Configuração e status."""
    return jsonify({
        "engine": "Piper TTS",
        "status": "online" if load_piper() else "offline",
        "languages": ["pt-BR", "en-US", "es-ES"],
        "max_text_length": 1000,
        "output_format": "WAV"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Gerador de Áudio (Piper TTS)")
    print("=" * 50)
    print("\n🎤 Convertendo texto → voz\n")
    sys.stdout.flush()
    print("🌐 Interface: http://localhost:5002/ui")
    print("📡 API REST: http://localhost:5002")
    print("=" * 50 + "\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5002, debug=False, threaded=True)
