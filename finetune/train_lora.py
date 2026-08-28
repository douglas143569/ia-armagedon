#!/usr/bin/env python3
"""Fase 6 — passo 2: treina um adaptador LoRA com o dataset do feedback.

Entrada : dataset.jsonl  (do build_dataset.py, formato {"messages": [...]})
Saída   : out/lora-armagedon/  (adaptador PEFT, poucos MB)

NÃO retreina o modelo todo — treina só ~0.1% dos pesos (matrizes LoRA de baixo posto).
Roda em CPU (lento) ou GPU (detecta sozinho). No PC do Douglas (CPU, 14GB), use um
modelo BASE pequeno (0.5B–1.5B). Pra 7B+ use GPU alugada (ver FASE-6-FINETUNING.md).

Config no topo do arquivo. Uso:
    python train_lora.py
    python train_lora.py --base Qwen/Qwen2.5-1.5B-Instruct --epochs 3
"""
import os, argparse, torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig
from trl import SFTTrainer, SFTConfig

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- padrões (bons pra CPU do Douglas) ------------------------------------
BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"   # pequeno de propósito; troque por 1.5B se aguentar
DATASET = os.path.join(HERE, "dataset.jsonl")
OUT_DIR = os.path.join(HERE, "out", "lora-armagedon")
EPOCHS = 3
LR = 2e-4
MAX_SEQ = 1024
LORA_R = 16
LORA_ALPHA = 32


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--epochs", type=float, default=EPOCHS)
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--max-seq", type=int, default=MAX_SEQ)
    args = ap.parse_args()

    if not os.path.exists(args.dataset):
        raise SystemExit(f"não achei {args.dataset} — rode build_dataset.py antes")

    has_cuda = torch.cuda.is_available()
    print(f"base={args.base} | dispositivo={'GPU' if has_cuda else 'CPU (vai ser lento)'}")

    tok = AutoTokenizer.from_pretrained(args.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.bfloat16 if has_cuda else torch.float32,
        device_map="auto" if has_cuda else None,
    )

    ds = load_dataset("json", data_files=args.dataset, split="train")
    print(f"exemplos: {len(ds)}")

    lora = LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=0.05,
        bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )

    cfg = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=args.lr,
        logging_steps=1,
        save_strategy="epoch",
        max_length=args.max_seq,     # trl >=1.0 (era max_seq_length antes)
        bf16=has_cuda,
        report_to=[],
        packing=False,
    )

    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds,
                         peft_config=lora, processing_class=tok)
    trainer.train()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    print(f"\nOK: adaptador LoRA salvo em {args.out}")
    print("Próximo passo: python to_ollama.py")


if __name__ == "__main__":
    main()
