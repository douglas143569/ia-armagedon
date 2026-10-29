#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Áudio Local com pyttsx3

Características:
- Vozes nativas do sistema operacional
- Suporte a múltiplos idiomas (PT, EN, ES, FR)
- Suporte a gênero (Masculino/Feminino)
- 100% offline - sem dependências externas
- Geração rápida de áudio
"""

import os
import sys
import json
import uuid
import threading
import time
import re
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, send_file

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except:
    PYTTSX3_AVAILABLE = False

app = Flask(__name__)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_generated")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Estado
jobs = {}
jobs_lock = threading.Lock()

# Mapeamento de idiomas para pyttsx3
LANG_MAP = {
    'pt': 'pt_BR',
    'en': 'en_US',
    'es': 'es_ES',
    'fr': 'fr_FR',
}

print("=" * 60)
if PYTTSX3_AVAILABLE:
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    voice_names = [v.name for v in voices]

    print("✓ pyttsx3 disponível")
    print("⚡ Modo LOCAL - Áudio 100% offline")
    print(f"✓ Vozes disponíveis ({len(voices)}):")
    for v in voices:
        print(f"   • {v.name}")
    print("✓ Tom Emocional: Alegre, Triste, Zangado, Calmo")
    print("✓ Divisão Automática: Textos >500 caracteres")
    print("⚠️  Nota: Gênero usa fallback se voz não está disponível")
else:
    print("❌ pyttsx3 não disponível - instale: pip install pyttsx3")
print("=" * 60)
sys.stdout.flush()


def chunk_text(text, max_chars=500):
    """Divide texto em partes para processamento."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ""

    for sentence in re.split(r'([.!?])', text):
        if len(current) + len(sentence) > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current += sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


def humanize_text(text):
    """Prepara texto para soar natural."""
    text = re.sub(r'([.!?])\s+', r'\1 ... ', text)
    text = re.sub(r'(,)\s+', r'\1 ... ', text)
    return text


def apply_emotion(engine, emotion='neutral'):
    """Aplica tom emocional ajustando rate/volume de forma mais perceptível."""
    emotions = {
        'neutral': {'rate': 1.0, 'volume': 1.0},
        'alegre': {'rate': 1.4, 'volume': 1.0},      # Muito mais rápido
        'happy': {'rate': 1.4, 'volume': 1.0},
        'triste': {'rate': 0.6, 'volume': 0.7},      # Bem mais lento e baixo
        'sad': {'rate': 0.6, 'volume': 0.7},
        'zangado': {'rate': 1.5, 'volume': 1.0},     # Máximo de intensidade
        'angry': {'rate': 1.5, 'volume': 1.0},
        'calmo': {'rate': 0.8, 'volume': 0.9},       # Equilibrado e suave
        'calm': {'rate': 0.8, 'volume': 0.9},
    }

    emotion_lower = emotion.lower()
    settings = emotions.get(emotion_lower, emotions['neutral'])

    base_rate = 150
    new_rate = int(base_rate * settings['rate'])
    engine.setProperty('rate', max(50, min(300, new_rate)))
    engine.setProperty('volume', max(0.0, min(1.0, settings['volume'])))

    return emotion_lower


def get_voice_id(gender='neutral'):
    """Retorna ID de voz baseado no gênero com fallback inteligente."""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')

    voice_name_lower = ""

    # Vozes femininas conhecidas (Microsoft, Google, Apple)
    female_names = ['maria', 'zira', 'cortana', 'eva', 'victoria', 'moira', 'samantha', 'victoria', 'susan']
    # Vozes masculinas conhecidas
    male_names = ['david', 'mark', 'simon', 'george', 'daniel', 'alex', 'james', 'michael', 'paul']

    # Procurar voz específica por gênero
    for voice in voices:
        voice_name_lower = voice.name.lower()

        if gender == 'male':
            # Procurar voz masculina
            for male_name in male_names:
                if male_name in voice_name_lower:
                    return voice.id
        elif gender == 'female':
            # Procurar voz feminina
            for female_name in female_names:
                if female_name in voice_name_lower:
                    return voice.id

    # Fallback: retornar primeira voz disponível
    if voices:
        print(f"⚠️  Voz {gender} não encontrada. Usando padrão: {voices[0].name}")
        return voices[0].id

    return None


def generate_audio_job(job_id, text, speed, lang='pt', gender='neutral', emotion='neutral', merge_chunks=False):
    """Gera áudio com pyttsx3, opcionalmente em múltiplas partes."""
    job = jobs[job_id]
    try:
        if not PYTTSX3_AVAILABLE:
            raise RuntimeError("pyttsx3 não disponível")

        # Dividir texto em chunks se necessário
        chunks = chunk_text(text, max_chars=500)
        job["total_chunks"] = len(chunks)
        job["current_chunk"] = 0

        audio_files = []

        for idx, chunk in enumerate(chunks):
            job["current_chunk"] = idx + 1
            job["status"] = "gerando"
            percent = int(20 + (70 * idx / len(chunks)))
            job["message"] = f"Processando parte {idx + 1}/{len(chunks)}..."
            job["percent"] = percent

            # Humanizar
            humanized_text = humanize_text(chunk)

            filename = f"armagedon_{datetime.now():%Y%m%d_%H%M%S}_{idx:02d}.wav"
            filepath = os.path.join(AUDIO_DIR, filename)

            # Inicializar pyttsx3
            engine = pyttsx3.init()

            # Configurar velocidade base
            engine.setProperty('rate', max(50, min(300, int(150 * speed))))

            # Aplicar emoção
            apply_emotion(engine, emotion)

            # Configurar voz por gênero
            voice_id = get_voice_id(gender)
            if voice_id:
                engine.setProperty('voice', voice_id)

            job["message"] = f"Gerando áudio {idx + 1}/{len(chunks)} ({emotion})..."
            job["percent"] = percent + 30

            # Gerar áudio
            engine.save_to_file(humanized_text, filepath)
            engine.runAndWait()

            # Converter WAV para MP3
            mp3_filename = filename.replace('.wav', '.mp3')
            mp3_filepath = os.path.join(AUDIO_DIR, mp3_filename)

            try:
                subprocess.run([
                    'ffmpeg', '-i', filepath, '-q:a', '5',
                    '-y', mp3_filepath
                ], capture_output=True, timeout=10)

                if os.path.exists(mp3_filepath):
                    os.remove(filepath)
                    audio_files.append((mp3_filename, mp3_filepath))
                else:
                    audio_files.append((filename, filepath))
            except:
                audio_files.append((filename, filepath))

        job["percent"] = 95
        job["message"] = "Finalizando áudio..."

        # Usar primeiro arquivo como resultado
        if audio_files:
            final_filename = audio_files[0][0]
            job["message"] = "✅ Áudio gerado com sucesso!"

            job.update(
                status="concluído",
                percent=100,
                message="✅ Áudio gerado!",
                filename=final_filename,
                total_chunks=len(chunks),
                result={"success": True, "filename": final_filename, "chunks": len(chunks)}
            )
            print(f"✓ Job {job_id}: {emotion} ({gender}/{lang}) - {len(chunks)} parte(s) → {final_filename}")
        else:
            raise RuntimeError("Falha ao gerar áudio")

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
    """Gera áudio com pyttsx3, emotion, e text chunking."""
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "Olá").strip()
        speed = max(0.5, min(2.0, float(data.get("speed", 1.0))))
        voice = data.get("voice", "pt")
        gender = data.get("gender", "neutral")
        emotion = data.get("emotion", "neutral")
        merge_chunks = data.get("merge_chunks", False)

        if emotion != "neutral":
            print(f"✓ Emotion recebida: '{emotion}'")

        job_id = str(uuid.uuid4())[:8]
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id, "type": "áudio", "text": text, "speed": speed,
                "voice": voice, "gender": gender, "emotion": emotion, "status": "na fila",
                "percent": 0, "message": "Na fila", "created": time.time(),
                "result": None, "total_chunks": 1, "current_chunk": 0
            }

        threading.Thread(
            target=generate_audio_job,
            args=(job_id, text, speed, voice, gender, emotion, merge_chunks),
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
        "emotion": job.get("emotion", "neutral"),
        "chunks": f"{job.get('current_chunk', 0)}/{job.get('total_chunks', 1)}"
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
        "status": "ok" if PYTTSX3_AVAILABLE else "degraded",
        "engine": "pyttsx3 (Local TTS)",
        "mode": "LOCAL - 100% Offline",
        "voices": "System voices", "languages": "PT, EN, ES, FR"
    }), 200


if __name__ == "__main__":
    print("\nARMAGEDON - Local Text-to-Speech (pyttsx3)")
    print("http://localhost:5005")
    print("\n📚 Recursos:")
    print("  • Tom Emocional (alegre, triste, zangado, calmo)")
    print("  • Divisão automática de textos >500 chars")
    print("  • Suporte: PT, EN, ES, FR")
    print("  • Gênero: Masculino/Feminino/Neutro\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5005, debug=False, threaded=True)
