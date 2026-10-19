#!/usr/bin/env python3
"""Diagnóstico completo de por que SD1.5 não funciona"""

import sys

print("\n" + "="*70)
print("DIAGNÓSTICO SD1.5 - INVESTIGAÇÃO COMPLETA")
print("="*70 + "\n")

# 1. Verificar PyTorch
print("1. PYTORCH")
print("-" * 70)
try:
    import torch
    print(f"✅ PyTorch importado")
    print(f"   Versão: {torch.__version__}")
    print(f"   CUDA disponível: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
    print(f"   CPU cores: {torch.get_num_threads()}")
except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)

# 2. Verificar Diffusers
print("\n2. DIFFUSERS")
print("-" * 70)
try:
    import diffusers
    print(f"✅ Diffusers importado")
    print(f"   Versão: {diffusers.__version__}")
except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)

# 3. Verificar transformers
print("\n3. TRANSFORMERS")
print("-" * 70)
try:
    import transformers
    print(f"✅ Transformers importado")
    print(f"   Versão: {transformers.__version__}")
except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)

# 4. Verificar memória
print("\n4. MEMÓRIA DISPONÍVEL")
print("-" * 70)
try:
    import psutil
    mem = psutil.virtual_memory()
    print(f"✅ RAM Total: {mem.total / 1e9:.1f}GB")
    print(f"   RAM Livre: {mem.available / 1e9:.1f}GB")
    print(f"   RAM em uso: {mem.percent}%")
except:
    print("⚠️  psutil não instalado, pulando")

# 5. Tentar carregar modelo
print("\n5. TENTANDO CARREGAR SD1.5")
print("-" * 70)

try:
    from diffusers import StableDiffusionPipeline

    print("Carregando runwayml/stable-diffusion-v1-5...")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    pipeline = StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float32,
        safety_checker=None,
        load_safety_checker=False
    )

    print("✅ Modelo carregado com sucesso!")

    pipeline = pipeline.to(device)
    print(f"✅ Modelo movido para {device}")

    # Testar geração
    print("\nTestando geração de imagem...")
    image = pipeline("test", num_inference_steps=1).images[0]
    print("✅ Geração de imagem funcionando!")

except OutOfMemoryError as e:
    print(f"❌ ERRO DE MEMÓRIA: {e}")
    print("   SOLUÇÃO: RAM insuficiente. Tente fechar outros programas.")

except Exception as e:
    print(f"❌ ERRO: {type(e).__name__}: {e}")
    import traceback
    print("\nTraceback completo:")
    traceback.print_exc()

print("\n" + "="*70)
print("FIM DO DIAGNÓSTICO")
print("="*70 + "\n")
