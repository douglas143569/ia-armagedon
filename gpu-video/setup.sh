#!/usr/bin/env bash
# ARMAGEDON - preparar uma GPU alugada (RunPod/Vast, Ubuntu) para gerar vídeo.
# Uso:  bash setup.sh            (usa CUDA 12.4; passe outra: bash setup.sh cu121)
set -e
CU="${1:-cu124}"
cd "$(dirname "$0")"

echo "== pacotes de sistema =="
apt-get update -y
apt-get install -y ffmpeg git python3-venv python3-pip

echo "== venv =="
python3 -m venv venv
source venv/bin/activate
pip install -U pip wheel

echo "== PyTorch ($CU) =="
pip install torch torchvision --index-url "https://download.pytorch.org/whl/${CU}"

echo "== libs de vídeo =="
pip install -r requirements-gpu.txt

echo "== baixando o modelo do preset (pode levar minutos) =="
python -c "from pipeline import preload; preload()"

echo
echo "PRONTO."
echo "  source venv/bin/activate"
echo "  python server.py            # sobe a API na porta 5001 (mesma do gerador local)"
echo "  # teste rapido, sem servidor:  python pipeline.py --prompt 'a neon city at night' --target-seconds 10"
