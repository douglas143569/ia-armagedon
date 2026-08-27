#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Vídeos/GIFs com Flask + Progresso Real"""
import os, sys, json, threading, time, uuid
from datetime import datetime
from flask import Flask, request, jsonify
import torch
from diffusers import StableDiffusionPipeline
from PIL import Image

app = Flask(__name__)
VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "videos_generated")
os.makedirs(VIDEOS_DIR, exist_ok=True)

# Store progress
jobs = {}

print("=" * 50)
print("🎬 ARMAGEDON - Gerador de Vídeos/GIFs")
print("=" * 50)
print("📥 Carregando modelo Stable Diffusion...")
sys.stdout.flush()

pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    torch_dtype=torch.float32,
    safety_checker=None,
)
pipe = pipe.to("cpu")
pipe.enable_attention_slicing()

print("✅ Modelo pronto!\n")
sys.stdout.flush()

def generate_video(job_id, prompt, duration, fps):
    """Gerar GIF com progresso real"""
    try:
        print(f"🎬 Job {job_id}: {prompt} ({duration}s, {fps}fps)")
        frames = []
        num_frames = max(2, duration * fps // 2)

        jobs[job_id] = {
            'status': 'gerando',
            'current': 0,
            'total': num_frames,
            'percent': 0,
            'message': 'Iniciando...'
        }

        for i in range(num_frames):
            jobs[job_id]['current'] = i + 1
            jobs[job_id]['percent'] = int((i + 1) / num_frames * 100)
            jobs[job_id]['message'] = f'Frame {i+1}/{num_frames}'

            print(f"   {jobs[job_id]['message']} ({jobs[job_id]['percent']}%)")

            with torch.no_grad():
                image = pipe(
                    prompt,
                    height=512,
                    width=512,
                    num_inference_steps=15,
                    guidance_scale=7.5
                ).images[0]
            frames.append(image)

        jobs[job_id]['message'] = 'Salvando GIF...'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"armagedon_{timestamp}.gif"
        filepath = os.path.join(VIDEOS_DIR, filename)

        frames[0].save(
            filepath,
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0
        )

        jobs[job_id]['status'] = 'concluído'
        jobs[job_id]['percent'] = 100
        jobs[job_id]['message'] = 'Concluído!'
        jobs[job_id]['filename'] = filename
        jobs[job_id]['result'] = {'success': True, 'filename': filename}

        print(f"✅ Job {job_id} salvo: {filepath}\n")

    except Exception as e:
        print(f"❌ Job {job_id} erro: {e}\n")
        jobs[job_id]['status'] = 'erro'
        jobs[job_id]['message'] = str(e)
        jobs[job_id]['result'] = {'success': False, 'error': str(e)}

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        prompt = data.get('prompt', 'landscape')
        duration = int(data.get('duration', 4))
        fps = int(data.get('fps', 6))

        job_id = str(uuid.uuid4())[:8]

        thread = threading.Thread(
            target=generate_video,
            args=(job_id, prompt, duration, fps),
            daemon=True
        )
        thread.start()

        return jsonify({'job_id': job_id}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/status/<job_id>', methods=['GET'])
def status(job_id):
    if job_id in jobs:
        job = jobs[job_id]
        response = {
            'status': job['status'],
            'percent': job['percent'],
            'current': job['current'],
            'total': job['total'],
            'message': job['message']
        }
        if job['status'] == 'concluído':
            response['result'] = job['result']
        elif job['status'] == 'erro':
            response['error'] = job['message']
        return jsonify(response), 200
    else:
        return jsonify({'error': 'Job não encontrado'}), 404

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    print("🌐 http://localhost:5001")
    print("⏸️  Pronto!\n")
    sys.stdout.flush()
    app.run(host='localhost', port=5001, debug=False, threaded=True)
