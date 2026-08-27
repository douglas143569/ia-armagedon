#!/usr/bin/env python3
"""ARMAGEDON - Gerador Final"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, sys
from datetime import datetime
import torch
from diffusers import StableDiffusionPipeline

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images_generated")
os.makedirs(IMAGES_DIR, exist_ok=True)

print("=" * 50)
print("🚀 ARMAGEDON - Gerador Final")
print("=" * 50)
print("📥 Carregando modelo...")
sys.stdout.flush()

pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    torch_dtype=torch.float32,
    safety_checker=None,
)
print("✅ Modelo baixado")
sys.stdout.flush()

pipe = pipe.to("cpu")
print("✅ Movido para CPU")
sys.stdout.flush()

pipe.enable_attention_slicing()
print("✅ Attention slicing OK")
sys.stdout.flush()

print("✅ Modelo pronto!\n")
sys.stdout.flush()

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/generate':
            try:
                # Ler e decodificar requisição
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length == 0:
                    raise ValueError("Content-Length é 0")

                body = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(body)
                prompt = data.get('prompt', 'landscape')

                print(f"🎨 Gerando: {prompt}")

                # Gerar imagem
                with torch.no_grad():
                    image = pipe(
                        prompt,
                        height=512,
                        width=512,
                        num_inference_steps=20,
                        guidance_scale=7.5
                    ).images[0]

                # Salvar
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"armagedon_{timestamp}.png"
                filepath = os.path.join(IMAGES_DIR, filename)
                image.save(filepath)

                print(f"✅ Salva: {filepath}\n")

                # Responder
                response = {
                    'success': True,
                    'message': 'Imagem gerada com sucesso',
                    'filename': filename,
                    'path': filepath
                }

                response_json = json.dumps(response)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_json)))
                self.end_headers()
                self.wfile.write(response_json.encode('utf-8'))

            except Exception as e:
                print(f"❌ Erro: {e}\n")
                response = {'success': False, 'error': str(e)}
                response_json = json.dumps(response)
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_json)))
                self.end_headers()
                self.wfile.write(response_json.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    print("🌐 http://localhost:5000")
    print("⏸️  Pronto! Pressione Ctrl+C para parar\n")

    server = HTTPServer(('localhost', 5000), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Parado")
