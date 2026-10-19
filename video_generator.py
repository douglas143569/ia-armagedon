#!/usr/bin/env python3
"""ARMAGEDON - Gerador de Vídeos com Stable Video Diffusion"""

from flask import Flask, request, jsonify
import os, time, tempfile
from PIL import Image, ImageDraw
import random

app = Flask(__name__)
os.makedirs("videos_generated", exist_ok=True)

pipeline = None
SVD_AVAILABLE = False

def load_svd():
    """Carrega Stable Video Diffusion"""
    global pipeline, SVD_AVAILABLE

    try:
        import torch
        from diffusers import StableVideoDiffusionPipeline

        print("\n" + "="*60)
        print("CARREGANDO STABLE VIDEO DIFFUSION")
        print("="*60)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Device: {device}")

        print("Carregando modelo...")

        pipeline = StableVideoDiffusionPipeline.from_pretrained(
            "stabilityai/stable-video-diffusion-img2vid-xt",
            torch_dtype=torch.float32
        )

        pipeline = pipeline.to(device)

        print("✅ SVD carregado com sucesso!")
        SVD_AVAILABLE = True
        return True

    except Exception as e:
        print(f"❌ Erro SVD: {e}")
        print("Usando fallback PIL...")
        SVD_AVAILABLE = False
        return False

def generate_with_svd(prompt, fps=15, duration=5):
    """Gera vídeo com SVD"""
    try:
        if not SVD_AVAILABLE or pipeline is None:
            return None

        print(f"Gerando vídeo com SVD: {prompt}")

        # Criar imagem inicial
        from PIL import Image as PILImage
        img = PILImage.new('RGB', (576, 1024), (100, 100, 100))

        video = pipeline(img, num_frames=fps*duration, num_inference_steps=25).frames[0]

        print("✅ Vídeo gerado com SVD!")
        return video

    except Exception as e:
        print(f"Erro SVD: {e}")
        return None

def generate_with_pil(prompt, fps=15, duration=5):
    """Gera vídeo animado com PIL"""
    try:
        import subprocess

        frames = fps * duration
        width, height = 512, 512

        print(f"Gerando {frames} frames a {fps} FPS...")

        colors = {
            'fogo': [(255, 69, 0), (255, 140, 0), (255, 215, 0)],
            'agua': [(0, 119, 182), (30, 144, 255), (173, 216, 230)],
            'natureza': [(34, 139, 34), (144, 238, 144), (107, 142, 35)],
        }

        palette = colors.get(prompt.split()[0].lower(), [(255, 107, 107), (76, 175, 80), (33, 150, 243)])

        frame_files = []
        tmp_dir = tempfile.gettempdir()

        for i in range(frames):
            img = Image.new('RGB', (width, height), (30, 30, 30))
            draw = ImageDraw.Draw(img)

            progress = i / frames

            for j in range(5):
                x = int((width/2 + 150 * random.random() * (progress + 0.5)) % width)
                y = int((height/2 + 150 * random.random() * (progress + 0.5)) % height)
                r = 30 + int(50 * (progress * (1 - progress)))

                color = palette[j % len(palette)]
                draw.ellipse([x-r, y-r, x+r, y+r], fill=color, outline=(200, 200, 200), width=2)

            bar_height = 20
            bar_width = int(width * progress)
            draw.rectangle([0, height-bar_height, bar_width, height], fill=(0, 255, 0))
            draw.text((10, height-bar_height+2), f"{int(progress*100)}%", fill=(255, 255, 255))

            fn = os.path.join(tmp_dir, f"frame_{i:04d}.png")
            img.save(fn)
            frame_files.append(fn)

            if i % 10 == 0:
                print(f"  Frame {i}/{frames}")

        output = f"videos_generated/video_{int(time.time())}.mp4"
        frame_pattern = os.path.join(tmp_dir, "frame_%04d.png")

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frame_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=60)

            for fn in frame_files:
                try:
                    os.remove(fn)
                except:
                    pass

            if os.path.exists(output):
                print(f"✅ Vídeo MP4: {output}")
                return output
        except:
            print("ffmpeg não disponível, criando GIF...")
            output = f"videos_generated/video_{int(time.time())}.gif"
            Image.open(frame_files[0]).save(
                output,
                save_all=True,
                append_images=[Image.open(f) for f in frame_files[1:]],
                duration=int(1000/fps),
                loop=0
            )

            for fn in frame_files:
                try:
                    os.remove(fn)
                except:
                    pass

            print(f"✅ Vídeo GIF: {output}")
            return output

        return None

    except Exception as e:
        print(f"Erro PIL: {e}")
        return None

@app.route("/health", methods=["GET"])
def health():
    engine = "SVD" if SVD_AVAILABLE else "PIL"
    return jsonify({"status": "ok", "engine": engine}), 200

@app.route("/jobs", methods=["GET"])
def jobs():
    return jsonify({"jobs": []}), 200

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt", "animation")
        fps = int(data.get("fps", 15))
        duration = int(data.get("duration", 5))

        print(f"\n{'='*60}")
        print(f"Gerando vídeo: {prompt}")
        print(f"FPS: {fps}, Duração: {duration}s")
        print(f"{'='*60}")

        video = None

        if SVD_AVAILABLE:
            video = generate_with_svd(prompt, fps, duration)

        if video is None:
            print("SVD falhou, usando PIL...")
            video = generate_with_pil(prompt, fps, duration)

        if video and os.path.exists(video):
            fn = os.path.basename(video)
            print(f"✅ Salvo: {fn}\n")
            return jsonify({"success": True, "filename": fn, "job_id": fn.split('.')[0]}), 200
        else:
            return jsonify({"error": "Falha ao gerar vídeo"}), 500

    except Exception as e:
        print(f"ERRO: {e}\n")
        return jsonify({"error": str(e)}), 500

@app.route("/status/<jid>", methods=["GET"])
def status(jid):
    return jsonify({"status": "concluido", "percent": 100}), 200

if __name__ == "__main__":
    print("\nARMAGEDON - Stable Video Diffusion")
    print("="*60)

    load_svd()

    if SVD_AVAILABLE:
        print("✅ SVD - Vídeos REALISTAS!")
        print("⏱️  Tempo: 1-2 minutos por vídeo\n")
    else:
        print("⚠️  SVD não carregou, usando PIL\n")

    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
