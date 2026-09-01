# Gerar vídeo (até ~1 min) numa GPU alugada — runbook

Kit pronto: você aluga a GPU, roda 2 comandos, e o ARMAGEDON usa ela pra vídeo.
Nada disso roda no seu PC (é CPU). Detalhe de modelos/VRAM em `models.md`.

---

## 1. Alugar a GPU

**RunPod** (mais fácil) → "Deploy" → GPU Pod → template **"RunPod PyTorch 2.x"** (Ubuntu + CUDA).

| Objetivo | GPU | preset (config.yaml) |
|---|---|---|
| Testar barato | RTX 4090 (24 GB) | `ltx` |
| Bom resultado | A100 80 GB | `wan` |
| Melhor aberto | H100 80 GB | `hunyuan` |

No deploy: **disco ≥ 60 GB**, e exponha a **porta TCP 5001** (RunPod: "Expose TCP Ports").

## 2. Preparar (uma vez por pod)

No terminal do pod:
```bash
git clone https://github.com/douglas143569/ia-armagedon
cd ia-armagedon/gpu-video
nano config.yaml          # ajuste `preset:` conforme a GPU (ver tabela acima)
bash setup.sh             # ~5-15 min: instala torch CUDA, diffusers, ffmpeg, baixa o modelo
```
> CUDA diferente de 12.4? `bash setup.sh cu121` (veja `nvidia-smi`).

## 3. Testar (sem o ARMAGEDON)
```bash
source venv/bin/activate
python pipeline.py --prompt "a neon city street at night, rain, cinematic" --target-seconds 15 --out teste.mp4
```
Saiu um `teste.mp4`? O modelo e a GPU estão ok. Ajuste `steps`/resolução no `config.yaml` se estiver lento.

## 4. Ligar o servidor
```bash
python server.py          # API na porta 5001 — mesma do gerador local
```
Deixe rodando. `GET http://SEU_POD:5001/health` deve responder.

## 5. Apontar o ARMAGEDON pra GPU

No **seu PC**, antes de subir o hub:
```powershell
$env:ARMAGEDON_VIDEO_URL = "http://SEU_POD_IP:PORTA_5001"
.\ARMAGEDON.bat
```
(RunPod te dá algo tipo `123.45.67.89:40000` → use esse par IP:porta.)
Ou, mais seguro, um **túnel SSH** e mantém a URL local:
```powershell
ssh -N -L 5001:localhost:5001 root@SEU_POD -p PORTA_SSH
# aí ARMAGEDON_VIDEO_URL nem precisa (fica localhost:5001)
```

Pronto: no painel **🎬 Vídeo** da interface, o campo "Duração" passa a valer **segundos-alvo do vídeo** (ex: 60). O hub manda pro pod, que gera os clipes, emenda e devolve o `.mp4`.

## 6. Ao terminar
- Baixe os vídeos (`gpu-video/videos_out/` no pod) antes de destruir o pod.
- **Destrua o pod** (RunPod: "Terminate") — cobrança é por hora.

---

## Notas
- 1 min ≈ 12 clipes de 5 s emendados pelo último frame. Deriva de cena acumula;
  para roteiro longo, gere por cena e monte num editor.
- `server.py` não descarrega o modelo entre jobs (numa GPU alugada isso é ok — você
  está pagando pra usar). Feche quando não estiver gerando.
- Este kit foi escrito sem GPU pra validar; na 1ª execução o ponto provável de ajuste
  é `build_pipe()` em `pipeline.py` (assinaturas mudam entre versões do diffusers).
