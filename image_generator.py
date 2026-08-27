#!/usr/bin/env python3
"""
ARMAGEDON - Gerador de Imagens
Servidor HTTP para gerar imagens com Stable Diffusion
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import json
import os
from datetime import datetime
import torch
from diffusers import StableDiffusionPipeline
from PIL import Image

# Criar pasta para salvar imagens
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images_generated")
os.makedirs(IMAGES_DIR, exist_ok=True)

print("=" * 50)
print("ARMAGEDON - Gerador de Imagens")
print("=" * 50)
print("\n📥 Carregando modelo Stable Diffusion...")
print("   Primeira vez demora 3-5 min...")

# Usar modelo leve para CPU
model_id = "runwayml/stable-diffusion-v1-5"

try:
    # Criar pipeline com otimizações para CPU
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float32,
        safety_checker=None,  # Desabilitar para velocidade
    )
    pipe = pipe.to("cpu")
    pipe.enable_attention_slicing()  # Economizar memória

    print("✅ Modelo carregado com sucesso!\n")
except Exception as e:
    print(f"❌ Erro ao carregar modelo: {e}")
    print("   Certifique-se que as dependências estão instaladas")
    exit(1)


class ImageGeneratorHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/generate':
            # Ler requisição
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body)
                prompt = data.get('prompt', 'a beautiful landscape')

                print(f"🎨 Gerando: {prompt}")
                print("   Aguarde... (1-3 minutos em CPU)")

                # Gerar imagem
                with torch.no_grad():
                    image = pipe(
                        prompt,
                        height=512,
                        width=512,
                        num_inference_steps=20,  # Menos passos = mais rápido
                        guidance_scale=7.5
                    ).images[0]

                # Salvar imagem
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"armagedon_{timestamp}.png"
                filepath = os.path.join(IMAGES_DIR, filename)
                image.save(filepath)

                print(f"✅ Imagem salva: {filepath}\n")

                # Retornar sucesso
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'success': True,
                    'message': 'Imagem gerada com sucesso',
                    'filename': filename,
                    'path': filepath
                }
                self.wfile.write(json.dumps(response).encode())

            except Exception as e:
                print(f"❌ Erro ao gerar imagem: {e}\n")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': False, 'error': str(e)}
                self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Desabilitar logs padrão
        pass


if __name__ == '__main__':
    PORT = 5000
    server = HTTPServer(('localhost', PORT), ImageGeneratorHandler)

    print(f"🌐 Servidor rodando em http://localhost:{PORT}")
    print("   Envie POST /generate com JSON: {\"prompt\": \"sua descrição\"}")
    print("\n⏸️  Pressione Ctrl+C para parar\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Servidor parado")
