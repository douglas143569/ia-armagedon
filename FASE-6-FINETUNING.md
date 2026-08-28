# FASE 6 — Fine-tuning (ARMAGEDON aprendendo de verdade)

Diferente de RAG/memória (que só colam contexto no prompt), aqui os **pesos do modelo
mudam**. Não é em tempo real: é um ciclo deliberado que você roda de vez em quando.

```
conversas → 👍/👎 na interface → brain_data/feedback.jsonl
          → build_dataset.py    → finetune/dataset.jsonl
          → train_lora.py       → finetune/out/lora-armagedon/  (adaptador, poucos MB)
          → to_ollama.py        → modelo "armagedon-tuned" no Ollama
          → (opcional) apontar o roteador / dropdown pra ele
```

## O que já está pronto

- **Botões 👍/👎** em cada resposta na interface. No 👎 aparece um campo "como deveria ter
  respondido" — é isso que vira o alvo de treino.
- Endpoints no cérebro (`armagedon_brain.py`): `POST /feedback`, `GET /feedback/stats`,
  `GET /feedback/recent`. Painel "🧠 Conhecimento" mostra a contagem.
- Dados em `brain_data/feedback.jsonl` (1 JSON por linha).

## Passo a passo

### 1. Coletar feedback
Use o ARMAGEDON normalmente. Dê 👍 nas respostas boas e 👎 + correção nas ruins.
Meta: **pelo menos 30–50 exemplos treináveis** (👍 com resposta, ou 👎 com correção).
Veja quanto tem no painel 🧠 Conhecimento ou em `GET /api/brain/feedback/stats`.

### 2. Montar o dataset
```
venv_images\Scripts\activate.bat
python finetune\build_dataset.py --min 30
```
Gera `finetune/dataset.jsonl` no formato chat (`messages`).

### 3. Treinar o LoRA

**Local (CPU do Douglas — só modelo pequeno):**
```
pip install -r finetune\requirements.txt
python finetune\train_lora.py --base Qwen/Qwen2.5-0.5B-Instruct --epochs 3
```
- 0.5B em CPU: ~alguns minutos a ~1h dependendo do nº de exemplos. 1.5B já fica pesado.
- Treina só ~0.1% dos pesos (matrizes LoRA). Saída: `finetune/out/lora-armagedon/`.

**GPU alugada (pra 7B+ — RunPod / Vast.ai, ~US$0,30/h):**
1. Suba um pod com PyTorch + CUDA
2. `pip install transformers peft datasets trl accelerate bitsandbytes`
3. Mande `finetune/` e `dataset.jsonl` pro pod
4. `python train_lora.py --base Qwen/Qwen2.5-7B-Instruct --epochs 2`
   (com GPU o script usa bf16 e `device_map=auto` sozinho)
5. Baixe `out/lora-armagedon/` de volta

### 4. Reintegrar no Ollama
```
git clone https://github.com/ggerganov/llama.cpp    (uma vez, em qualquer pasta)
python finetune\to_ollama.py --base Qwen/Qwen2.5-0.5B-Instruct --llamacpp C:\caminho\llama.cpp
```
Faz merge do LoRA no base, converte pra GGUF e roda `ollama create armagedon-tuned`.
Teste: `ollama run armagedon-tuned`.

Só quer testar o adaptador sem GGUF? `python finetune\to_ollama.py --merge-only` e carregue
`finetune/out/merged/` com `transformers`.

### 5. Adotar (opcional)
Se ficou bom, edite `armagedon_brain.py` (`MODEL_DEFAULT`) ou adicione `armagedon-tuned`
no dropdown do `interface.html`. Guarde o `dataset.jsonl` de cada rodada pra treinar
acumulando (dataset novo = antigos + feedback recente).

## Cuidados

- **Poucos exemplos + muitas épocas = decoreba** (overfitting): o modelo repete as respostas
  do dataset e piora no resto. Comece com 3 épocas e `lr 2e-4`; se decorar, baixe pra 1–2.
- Fine-tune ensina **estilo e formato** muito bem; ensina **fato novo** mal — pra fato use RAG/memória.
- Sempre teste a versão nova lado a lado com a antiga antes de adotar.
- Mantenha o `feedback.jsonl` versionado num backup — é o ativo que você está construindo.
