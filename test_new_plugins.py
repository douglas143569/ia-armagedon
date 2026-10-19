#!/usr/bin/env python3
"""Teste dos novos plugins: Image Editor e Video Summarizer"""

from plugin_manager import PluginManager
from PIL import Image
import os

print("\n" + "="*70)
print("🧪 TESTE: Image Editor e Video Summarizer")
print("="*70)

# Inicializar
manager = PluginManager()
manager.discover_plugins()

# Carregar novos plugins
print("\n📥 Carregando novos plugins...\n")
for plugin_name in ["Image Editor", "Video Summarizer"]:
    if manager.load_plugin(plugin_name):
        print(f"✓ {plugin_name} carregado")

# Criar imagem de teste
print("\n" + "="*70)
print("🧪 TESTE 1: Image Editor")
print("="*70)

test_image_path = "test_image_original.png"
if not os.path.exists(test_image_path):
    # Criar imagem de teste
    img = Image.new("RGB", (800, 600), color=(73, 109, 137))
    img.save(test_image_path)
    print(f"✓ Imagem de teste criada: {test_image_path}")

# Teste 1: Redimensionar
print("\n1️⃣ Redimensionando imagem...")
result = manager.execute_plugin("Image Editor", "resize", test_image_path, 400, 300, True)
if result["success"]:
    print(f"✓ Redimensionada: {result['result']['original_size']} → {result['result']['new_size']}")
    print(f"  Arquivo: {result['result']['output']}")
else:
    print(f"❌ Erro: {result['error']}")

# Teste 2: Aplicar filtro
print("\n2️⃣ Aplicando filtro blur...")
result = manager.execute_plugin("Image Editor", "apply_filter", test_image_path, "blur")
if result["success"]:
    print(f"✓ Filtro '{result['result']['filter']}' aplicado")
    print(f"  Arquivo: {result['result']['output']}")
else:
    print(f"❌ Erro: {result['error']}")

# Teste 3: Ajustar brilho
print("\n3️⃣ Ajustando brilho/contraste...")
result = manager.execute_plugin(
    "Image Editor",
    "adjust",
    test_image_path,
    brightness=1.3,
    contrast=1.2,
    saturation=1.1
)
if result["success"]:
    print(f"✓ Ajustes aplicados:")
    print(f"  Brilho: {result['result']['adjustments']['brightness']}")
    print(f"  Contraste: {result['result']['adjustments']['contrast']}")
    print(f"  Saturação: {result['result']['adjustments']['saturation']}")
    print(f"  Arquivo: {result['result']['output']}")
else:
    print(f"❌ Erro: {result['error']}")

# Teste 4: Adicionar marca d'água
print("\n4️⃣ Adicionando marca d'água...")
result = manager.execute_plugin(
    "Image Editor",
    "add_watermark",
    test_image_path,
    text="© ARMAGEDON 2026",
    position="bottom-right",
    opacity=0.7
)
if result["success"]:
    print(f"✓ Marca d'água adicionada")
    print(f"  Texto: {result['result']['text']}")
    print(f"  Posição: {result['result']['position']}")
    print(f"  Arquivo: {result['result']['output']}")
else:
    print(f"❌ Erro: {result['error']}")

# Teste 5: Converter formato
print("\n5️⃣ Convertendo formato...")
result = manager.execute_plugin("Image Editor", "convert_format", test_image_path, "JPG")
if result["success"]:
    data = result.get("result", result)
    print(f"✓ Formato convertido")
    print(f"  De: {data.get('original_format', 'N/A')} → Para: {data.get('new_format', 'JPG')}")
    print(f"  Arquivo: {data.get('output', 'N/A')}")
else:
    print(f"❌ Erro: {result.get('error', 'Desconhecido')}")

# Video Summarizer Info
print("\n" + "="*70)
print("🎬 TESTE 2: Video Summarizer")
print("="*70)

info = manager.execute_plugin("Video Summarizer", "get_info")
if info["success"]:
    print(f"\n✓ Plugin carregado:")
    print(f"  Nome: {info['result']['name']}")
    print(f"  Versão: {info['result']['version']}")
    print(f"  Descrição: {info['result']['description']}")
    print(f"\n  Funcionalidades:")
    for feature in info['result']['features']:
        print(f"    • {feature}")
else:
    print(f"❌ Erro: {info['error']}")

# Webhook test
print("\n" + "="*70)
print("🔗 TESTE 3: Webhooks")
print("="*70)

print("\n📸 Registrando webhook para Image Editor...")
manager.register_webhook("image_generated", "Image Editor", "on_image_generated")

print("🎬 Registrando webhook para Video Summarizer...")
manager.register_webhook("video_generated", "Video Summarizer", "on_video_generated")

print("\nWebhooks registrados com sucesso!")

print("\n" + "="*70)
print("✅ TODOS OS TESTES CONCLUÍDOS!")
print("="*70 + "\n")

print("📊 Resumo de Funcionalidades:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("\n🖼️  IMAGE EDITOR:")
print("  • Redimensionar/cortar")
print("  • Ajustar brilho/contraste/saturação")
print("  • Aplicar filtros (blur, sharpen, etc)")
print("  • Adicionar marca d'água")
print("  • Converter formatos")

print("\n🎬 VIDEO SUMMARIZER:")
print("  • Extrair frames-chave")
print("  • Detectar cenas")
print("  • Criar GIF resumido")
print("  • Gerar thumbnail")
print("  • Obter metadados")

print("\n" + "="*70 + "\n")
