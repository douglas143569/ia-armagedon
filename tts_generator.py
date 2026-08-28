#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Áudio com pyttsx3 + Vozes por Gênero

Usa vozes nativas do Windows com suporte real a:
- Múltiplos idiomas
- Gênero (Masculino/Feminino/Neutro)
- Velocidade ajustável
"""

import os
import sys
import json
import uuid
import threading
import time
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import pyttsx3

app = Flask(__name__)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_generated")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Estado do TTS
jobs = {}
jobs_lock = threading.Lock()

# Inicializar pyttsx3
try:
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)

    # Listar vozes disponíveis
    voices = engine.getProperty('voices')
    print(f"✓ pyttsx3 pronto com {len(voices)} vozes:")
    for i, voice in enumerate(voices):
        print(f"  {i}: {voice.name} ({voice.id})")
    sys.stdout.flush()
except Exception as e:
    engine = None
    print(f"❌ Erro ao carregar pyttsx3: {e}")
    sys.stdout.flush()


def humanize_text(text):
    """Prepara texto para soar mais natural."""
    text = re.sub(r'([.!?])\s+', r'\1 ... ', text)
    text = re.sub(r'(,)\s+', r'\1 ... ', text)
    text = text.replace("Dr.", "Doutor")
    text = text.replace("Sr.", "Senhor")
    return text


def get_voice_id(gender='neutral'):
    """Seleciona a voz apropriada por gênero."""
    try:
        voices = engine.getProperty('voices')

        # Procurar por vozes específicas
        for voice in voices:
            voice_name = voice.name.lower()

            if gender == 'male':
                if 'david' in voice_name or 'mark' in voice_name or 'paulo' in voice_name or 'george' in voice_name:
                    return voice.id
            elif gender == 'female':
                if 'zira' in voice_name or 'maria' in voice_name or 'victoria' in voice_name or 'cortana' in voice_name or 'eva' in voice_name:
                    return voice.id

        # Se não encontrar específica, usar a primeira disponível
        return voices[0].id if voices else None
    except:
        return None


def generate_audio_job(job_id, text, speed, lang='pt', gender='neutral'):
    """Gera áudio em background com vozes reais."""
    job = jobs[job_id]
    try:
        if not engine:
            raise RuntimeError("pyttsx3 não disponível")

        job["status"] = "gerando"
        job["message"] = "Processando texto..."
        job["percent"] = 20

        # Humanizar texto
        if lang.startswith('pt'):
            humanized_text = humanize_text(text)
        else:
            humanized_text = text

        job["percent"] = 40
        gender_label = {'male': 'Masculina', 'female': 'Feminina', 'neutral': 'Neutra'}
        job["message"] = f"Voz {gender_label.get(gender, 'Neutra')} ({lang.upper()})..."

        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)

        # Configurar voz
        voice_id = get_voice_id(gender)
        if voice_id:
            engine.setProperty('voice', voice_id)

        # Configurar velocidade
        rate = int(150 * speed)
        engine.setProperty('rate', rate)

        job["percent"] = 70
        job["message"] = "Gerando áudio com voz real..."

        # Gerar áudio
        engine.save_to_file(humanized_text, filepath)
        engine.runAndWait()

        job["percent"] = 90
        job["message"] = "Finalizando..."

        time.sleep(0.5)

        job.update(
            status="concluído",
            percent=100,
            message="✅ Voz real gerada!",
            filename=filename,
            result={"success": True, "filename": filename}
        )
        print(f"✓ Job {job_id} concluído ({gender}): {filepath}")

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
        voice = data.get("voice", "pt")
        gender = data.get("gender", "neutral")

        if len(text) > 500:
            return jsonify({"error": "Texto muito longo (máx 500 caracteres)"}), 400

        job_id = str(uuid.uuid4())[:8]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id,
                "type": "áudio",
                "text": text,
                "speed": speed,
                "voice": voice,
                "gender": gender,
                "status": "na fila",
                "percent": 0,
                "message": "Na fila",
                "created": time.time(),
                "result": None
            }

        threading.Thread(
            target=generate_audio_job,
            args=(job_id, text, speed, voice, gender),
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
        "status": "ok" if engine else "error",
        "engine": "pyttsx3 com Vozes Reais",
        "features": ["Vozes do Windows", "Gênero (M/F)", "Humanização"]
    }), 200


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Gerador de Áudio (Vozes Reais)")
    print("=" * 50)
    print("\n🎤 Vozes Reais do Windows\n")
    sys.stdout.flush()
    print("http://localhost:5002")
    print("=" * 50 + "\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5002, debug=False, threaded=True)
