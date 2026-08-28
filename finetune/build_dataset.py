#!/usr/bin/env python3
"""Fase 6 — passo 1: transforma o feedback (👍/👎) num dataset de fine-tuning.

Entrada : ../brain_data/feedback.jsonl   (gerado pela interface)
Saída   : dataset.jsonl                  (formato chat/messages, pronto pro train_lora.py)

Regra:
  - 👍 (rating "up")   -> exemplo positivo: alvo = a própria resposta que o modelo deu
  - 👎 (rating "down") COM correção -> exemplo: alvo = a correção que Douglas escreveu
  - 👎 sem correção    -> descartado (não dá pra ensinar sem saber a resposta certa)

Uso:  python build_dataset.py            (usa o feedback.jsonl padrão)
      python build_dataset.py --min 20  (aborta se tiver menos de 20 exemplos)
"""
import os, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDBACK = os.path.join(HERE, "..", "brain_data", "feedback.jsonl")
OUT = os.path.join(HERE, "dataset.jsonl")

SYSTEM = ("Você é o ARMAGEDON, assistente de IA pessoal de Douglas. "
          "Responda em português brasileiro, de forma clara, direta e útil.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback", default=FEEDBACK)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--min", type=int, default=1, help="mínimo de exemplos pra não abortar")
    args = ap.parse_args()

    if not os.path.exists(args.feedback):
        raise SystemExit(f"não achei {args.feedback} — dê alguns 👍/👎 na interface primeiro")

    exemplos = []
    with open(args.feedback, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            prompt = (r.get("prompt") or "").strip()
            if not prompt:
                continue
            if r.get("rating") == "up":
                alvo = (r.get("response") or "").strip()
            elif r.get("rating") == "down":
                alvo = (r.get("correction") or "").strip()
            else:
                continue
            if not alvo:
                continue
            exemplos.append({
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": alvo},
                ]
            })

    if len(exemplos) < args.min:
        raise SystemExit(f"só {len(exemplos)} exemplos treináveis (mínimo {args.min}). "
                         "Colete mais feedback antes de treinar.")

    with open(args.out, "w", encoding="utf-8") as f:
        for e in exemplos:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"OK: {len(exemplos)} exemplos -> {args.out}")


if __name__ == "__main__":
    main()
