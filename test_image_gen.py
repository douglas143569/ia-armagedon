#!/usr/bin/env python3
"""Teste detalhado do gerador de imagens"""

import sys, os

print("\n" + "="*70)
print("TESTE DETALHADO - POR QUE IMAGEM É ABSTRATA?")
print("="*70 + "\n")

# 1. Verificar arquivo
print("1. VERIFICANDO ARQUIVO")
print("-" * 70)
if os.path.exists("image_generator.py"):
    print("✅ image_generator.py existe")
    with open("image_generator.py", "r", encoding="utf-8") as f:
        content = f.read()
        if "def generate_with_sd" in content:
            print("✅ Função generate_with_sd existe")
        else:
            print("❌ Função generate_with_sd NÃO ENCONTRADA")

        if "from diffusers import StableDiffusionPipeline" in content:
            print("✅ Import de StableDiffusionPipeline existe")
        else:
            print("❌ Import de StableDiffusionPipeline NÃO ENCONTRADO")
else:
    print("❌ image_generator.py NÃO ENCONTRADO!")
    sys.exit(1)

# 2. Verificar se consegue importar bibliotecas
print("\n2. TESTANDO IMPORTS")
print("-" * 70)

try:
    import torch
    print(f"✅ PyTorch {torch.__version__}")
except Exception as e:
    print(f"❌ PyTorch: {e}")
    sys.exit(1)

try:
    from diffusers import StableDiffusionPipeline
    print("✅ Diffusers StableDiffusionPipeline")
except Exception as e:
    print(f"❌ Diffusers: {e}")
    sys.exit(1)

# 3. Tentar carregar modelo
print("\n3. CARREGANDO MODELO SD1.5")
print("-" * 70)

try:
    print("Carregando runwayml/stable-diffusion-v1-5...")

    pipeline = StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float32,
        safety_checker=None,
        load_safety_checker=False
    )

    print("✅ Modelo carregado!")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = pipeline.to(device)
    print(f"✅ Modelo movido para {device}")

    # 4. Tentar gerar imagem
    print("\n4. TESTANDO GERAÇÃO")
    print("-" * 70)
    print("Gerando imagem teste...")

    image = pipeline("a beautiful woman, photorealistic", num_inference_steps=5).images[0]

    print("✅ IMAGEM GERADA COM SUCESSO!")
    print("✅✅✅ SD1.5 ESTÁ FUNCIONANDO!")

    image.save("test_output.png")
    print("✅ Imagem salva em test_output.png")

except Exception as e:
    print(f"❌ ERRO: {type(e).__name__}: {e}")
    print("\nISTO SIGNIFICA QUE SD1.5 NÃO CARREGA")
    print("Por isso imagem sai ABSTRATA (fallback PIL)")

print("\n" + "="*70)
print("FIM DO TESTE")
print("="*70 + "\n")
