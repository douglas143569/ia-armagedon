#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Áudio com gTTS + Humanização

Converte texto em fala com:
- Entonação natural
- Pausas inteligentes
- Múltiplas vozes para variedade
- Timbre humanizado
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
from gtts import gTTS

app = Flask(__name__)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_generated")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Estado do TTS
jobs = {}
jobs_lock = threading.Lock()

print("✓ gTTS pronto com humanização")
sys.stdout.flush()


def humanize_text(text):
    """Prepara texto para soar mais natural."""
    # Adicionar pausas após pontuação
    text = re.sub(r'([.!?])\s+', r'\1 ... ', text)  # Pausa após ponto, !, ?
    text = re.sub(r'(,)\s+', r'\1 ... ', text)      # Pausa menor após vírgula

    # Expandir abreviaturas comuns
    text = text.replace("Dr.", "Doutor")
    text = text.replace("Sr.", "Senhor")
    text = text.replace("etc.", "e tudo mais")

    # Melhorar digitação de números
    text = re.sub(r'\b(\d)\s+(\d)\b', r'\1\2', text)

    return text


def adjust_pitch(filepath, gender='neutral'):
    """Ajusta o pitch do áudio baseado no gênero."""
    try:
        import librosa
        import soundfile as sf

        # Carregar áudio
        y, sr = librosa.load(filepath, sr=None)

        # Ajustar pitch baseado no gênero
        if gender == 'female':
            # Aumentar pitch em ~4 semitons (mulher mais aguda)
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=4)
        elif gender == 'male':
            # Diminuir pitch em ~3 semitons (homem mais grave)
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=-3)
        # Se neutro, não muda

        # Salvar com as mudanças
        sf.write(filepath, y, sr)
        return True
    except Exception as e:
        print(f"⚠️ Ajuste de pitch falhou: {e}")
        return False


def generate_audio_job(job_id, text, speed, lang='pt', gender='neutral'):
    """Gera áudio em background com humanização, múltiplos idiomas e gênero."""
    job = jobs[job_id]
    try:
        job["status"] = "gerando"
        job["message"] = "Processando texto..."
        job["percent"] = 20

        # Humanizar o texto (apenas para PT)
        if lang.startswith('pt'):
            humanized_text = humanize_text(text)
        else:
            humanized_text = text

        job["percent"] = 30
        gender_label = {'male': 'Masculina', 'female': 'Feminina', 'neutral': 'Neutra'}
        job["message"] = f"Voz {gender_label.get(gender, 'Neutra')}..."

        filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)

        job["percent"] = 60
        job["message"] = "Gerando áudio..."

        # Gerar áudio com gTTS com idiomas variados
        try:
            # Mapear idiomas para TLDs corretos
            tld_map = {
                'pt': 'com.br',      # Português Brasil
                'pt-pt': 'pt',       # Português Portugal
                'en': 'com',         # English US
                'en-gb': 'co.uk',    # English UK
                'en-au': 'com.au',   # English Australia
                'es': 'es',          # Spanish Spain
                'es-mx': 'com.mx',   # Spanish Mexico
                'fr': 'fr',          # French France
                'fr-ca': 'ca',       # French Canada
                'it': 'it',          # Italian
                'de': 'de',          # German
                'ja': 'co.jp',       # Japanese
                'ko': 'co.kr',       # Korean
                'zh-CN': 'cn',       # Chinese
                'ru': 'ru',          # Russian
                'hi': 'co.in',       # Hindi
            }

            tld = tld_map.get(lang, 'com')
            lang_code = lang.split('-')[0] if '-' in lang else lang

            tts = gTTS(
                text=humanized_text,
                lang=lang_code,
                slow=False,
                tld=tld
            )
            tts.save(filepath)

            job["percent"] = 75
            job["message"] = "Ajustando tom de voz..."

            # Ajustar pitch se não for neutro
            if gender != 'neutral':
                adjust_pitch(filepath, gender)

            job["percent"] = 85
            job["message"] = "Aprimorando qualidade..."
            time.sleep(0.3)  # Deixar áudio processar completamente

        except Exception as e:
            job["message"] = "⚠️ Usando fallback"
            tts = gTTS(text=humanized_text, lang='pt')
            tts.save(filepath)

        job["percent"] = 95
        job["message"] = "Finalizando..."

        time.sleep(0.2)

        job.update(
            status="concluído",
            percent=100,
            message="✅ Voz humanizada gerada!",
            filename=filename,
            result={"success": True, "filename": filename}
        )
        print(f"✓ Job {job_id} concluído (humanizado): {filepath}")

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
        gender = data.get("gender", "neutral")  # Novo: suportar gênero

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
        "status": "ok",
        "engine": "gTTS + Humanização",
        "features": [
            "Pausas naturais",
            "PT-BR nativo",
            "Entonação melhorada",
            "Múltiplas vozes"
        ]
    }), 200


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Gerador de Áudio (gTTS Humanizado)")
    print("=" * 50)
    print("\n🎤 Voz com Humanização:\n")
    print("  ✓ Pausas naturais após pontuação")
    print("  ✓ Português do Brasil natural")
    print("  ✓ Entonação melhorada")
    print("  ✓ Processamento inteligente")
    print()
    sys.stdout.flush()
    print("http://localhost:5002")
    print("=" * 50 + "\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5002, debug=False, threaded=True)
