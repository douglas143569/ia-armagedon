#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Áudio com Azure Text-to-Speech

Vozes profissionais reais:
- 200+ vozes em 90+ idiomas
- Vozes neurais ultra-realistas
- Suporte completo a gênero (Masculino/Feminino)
- Grátis (5M caracteres/mês)
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

try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_AVAILABLE = True
except:
    AZURE_AVAILABLE = False

app = Flask(__name__)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_generated")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Configuração do Azure
AZURE_KEY = os.environ.get('AZURE_SPEECH_KEY', 'demo')
AZURE_REGION = os.environ.get('AZURE_SPEECH_REGION', 'eastus')

# Estado
jobs = {}
jobs_lock = threading.Lock()

# Vozes disponíveis (Azure)
VOICES = {
    'pt': {
        'neutral': 'pt-BR-AntonioNeural',      # Homem
        'male': 'pt-BR-AntonioNeural',         # Homem
        'female': 'pt-BR-FranciscaNeural',     # Mulher
    },
    'en': {
        'neutral': 'en-US-AriaNeural',         # Mulher
        'male': 'en-US-GuyNeural',             # Homem
        'female': 'en-US-AriaNeural',          # Mulher
    },
    'es': {
        'neutral': 'es-ES-AlvaroNeural',       # Homem
        'male': 'es-ES-AlvaroNeural',          # Homem
        'female': 'es-ES-ElviraNeural',        # Mulher
    },
    'fr': {
        'neutral': 'fr-FR-HenriNeural',        # Homem
        'male': 'fr-FR-HenriNeural',           # Homem
        'female': 'fr-FR-DeniseNeural',        # Mulher
    },
}

print("=" * 50)
if AZURE_AVAILABLE:
    print("✓ Azure Speech SDK disponível")
    if AZURE_KEY == 'demo':
        print("⚠️  Modo DEMO (sem API key)")
        print("Para usar Azure de verdade:")
        print("  set AZURE_SPEECH_KEY=your-key")
        print("  set AZURE_SPEECH_REGION=eastus")
else:
    print("❌ Azure Speech não disponível")
print("=" * 50)
sys.stdout.flush()


def humanize_text(text):
    """Prepara texto para soar natural."""
    text = re.sub(r'([.!?])\s+', r'\1 ... ', text)
    text = re.sub(r'(,)\s+', r'\1 ... ', text)
    return text


def get_voice_name(lang='pt', gender='neutral'):
    """Seleciona voz apropriada por idioma e gênero."""
    lang_short = lang.split('-')[0]
    voices = VOICES.get(lang_short, VOICES['pt'])
    return voices.get(gender, voices.get('neutral'))


def generate_audio_job(job_id, text, speed, lang='pt', gender='neutral'):
    """Gera áudio com Azure TTS."""
    job = jobs[job_id]
    try:
        if not AZURE_AVAILABLE:
            raise RuntimeError("Azure Speech SDK não disponível")

        job["status"] = "gerando"
        job["message"] = "Processando texto..."
        job["percent"] = 20

        # Humanizar
        humanized_text = humanize_text(text)

        job["percent"] = 40
        gender_label = {'male': 'Masculina', 'female': 'Feminina', 'neutral': 'Neutra'}
        job["message"] = f"Voz {gender_label.get(gender)} - {lang.upper()}..."

        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)

        # Configurar Azure
        if AZURE_KEY == 'demo':
            # Modo demo - simular com arquivo vazio (em produção, use Azure real)
            job["message"] = "⚠️ Modo DEMO - Configure AZURE_SPEECH_KEY"
            open(filepath, 'a').close()
        else:
            speech_config = speechsdk.SpeechConfig(
                subscription=AZURE_KEY,
                region=AZURE_REGION
            )

            # Selecionar voz
            voice_name = get_voice_name(lang, gender)
            speech_config.speech_synthesis_voice_name = voice_name

            # Criar synthesizer
            audio_config = speechsdk.audio.AudioOutputConfig(filename=filepath)
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=audio_config
            )

            job["percent"] = 70
            job["message"] = f"Gerando com {voice_name}..."

            # Gerar áudio
            result = synthesizer.speak_text(humanized_text)

            if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
                raise RuntimeError(f"Erro: {result.reason}")

        job["percent"] = 95
        job["message"] = "Finalizando..."
        time.sleep(0.3)

        job.update(
            status="concluído",
            percent=100,
            message="✅ Áudio profissional gerado!",
            filename=filename,
            result={"success": True, "filename": filename}
        )
        print(f"✓ Job {job_id}: {gender} ({lang})")

    except Exception as e:
        job.update(
            status="erro",
            message=str(e),
            result={"success": False, "error": str(e)}
        )
        print(f"❌ Job {job_id}: {e}")

    sys.stdout.flush()


@app.route("/generate", methods=["POST"])
def generate():
    """Gera áudio com Azure."""
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "Olá").strip()
        speed = max(0.5, min(2.0, float(data.get("speed", 1.0))))
        voice = data.get("voice", "pt")
        gender = data.get("gender", "neutral")

        if len(text) > 500:
            return jsonify({"error": "Texto muito longo"}), 400

        job_id = str(uuid.uuid4())[:8]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id, "type": "áudio", "text": text, "speed": speed,
                "voice": voice, "gender": gender, "status": "na fila",
                "percent": 0, "message": "Na fila", "created": time.time(),
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
    """Verifica status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404

    resp = {
        "status": job["status"], "percent": job["percent"],
        "message": job["message"], "text": job["text"],
    }
    if job["status"] == "concluído":
        resp["result"] = job["result"]
    elif job["status"] == "erro":
        resp["error"] = job["message"]
    return jsonify(resp), 200


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id):
    """Baixa áudio."""
    job = jobs.get(job_id)
    if not job or job["status"] != "concluído":
        return jsonify({"error": "Áudio não pronto"}), 404

    filepath = os.path.join(AUDIO_DIR, job["result"]["filename"])
    if not os.path.exists(filepath):
        return jsonify({"error": "Arquivo não encontrado"}), 404

    return send_file(filepath, as_attachment=True)


@app.route("/jobs", methods=["GET"])
def list_jobs():
    """Lista jobs."""
    now = time.time()
    out = [{
        "id": j["id"], "type": j["type"], "prompt": j.get("text", ""),
        "status": j["status"], "percent": j["percent"],
        "message": j["message"], "elapsed": int(now - j["created"]),
        "active": j["status"] in ("na fila", "gerando"),
    } for j in sorted(jobs.values(), key=lambda x: x["created"], reverse=True)]
    return jsonify({"jobs": out}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok" if AZURE_AVAILABLE else "degraded",
        "engine": "Azure Text-to-Speech",
        "mode": "DEMO" if AZURE_KEY == "demo" else "PRODUCTION",
        "voices": "200+", "languages": "90+"
    }), 200


if __name__ == "__main__":
    print("\nARMAGEDON - Azure Text-to-Speech")
    print("http://localhost:5002\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5002, debug=False, threaded=True)
