#!/usr/bin/env python3
r"""Fase 6 — passo 3: junta o LoRA no modelo base e registra no Ollama.

Faz:
  1. carrega o base + adaptador LoRA (out/lora-armagedon/) e faz o merge dos pesos
  2. salva o modelo merjado em out/merged/
  3. converte pra GGUF com o llama.cpp (precisa do repo llama.cpp clonado — ver abaixo)
  4. gera um Modelfile e roda `ollama create armagedon-tuned`

Pré-requisito pro passo 3-4: clonar o llama.cpp uma vez —
    git clone https://github.com/ggerganov/llama.cpp  (numa pasta qualquer)
e passar o caminho:  python to_ollama.py --llamacpp C:\caminho\llama.cpp

Se você só quer testar o adaptador sem GGUF, rode com --merge-only e carregue
out/merged/ direto com transformers.
"""
import os, sys, argparse, subprocess, shutil, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

HERE = os.path.dirname(os.path.abspath(__file__))
LORA_DIR = os.path.join(HERE, "out", "lora-armagedon")
MERGED_DIR = os.path.join(HERE, "out", "merged")
GGUF_PATH = os.path.join(HERE, "out", "armagedon-tuned.gguf")
MODELFILE = os.path.join(HERE, "out", "Modelfile.tuned")
BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
OLLAMA_NAME = "armagedon-tuned"

SYSTEM = ("Você é o ARMAGEDON, assistente de IA pessoal de Douglas. "
          "Responda em português brasileiro, de forma clara, direta e útil.")


def merge(base, lora_dir, out):
    print(f"merge: {base} + {lora_dir}")
    tok = AutoTokenizer.from_pretrained(lora_dir if os.path.exists(
        os.path.join(lora_dir, "tokenizer_config.json")) else base)
    model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.float16)
    model = PeftModel.from_pretrained(model, lora_dir)
    model = model.merge_and_unload()
    os.makedirs(out, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    print(f"OK: modelo merjado em {out}")


def to_gguf(merged, gguf, llamacpp):
    conv = os.path.join(llamacpp, "convert_hf_to_gguf.py")
    if not os.path.exists(conv):
        raise SystemExit(f"não achei {conv} — clone o llama.cpp e passe --llamacpp")
    print("convertendo pra GGUF (q8_0)...")
    subprocess.run([sys.executable, conv, merged, "--outfile", gguf,
                    "--outtype", "q8_0"], check=True)
    print(f"OK: {gguf}")


def register(gguf, modelfile, name):
    with open(modelfile, "w", encoding="utf-8") as f:
        f.write(f'FROM {gguf}\n\nSYSTEM """{SYSTEM}"""\n\n'
                "PARAMETER temperature 0.7\nPARAMETER top_p 0.9\n")
    subprocess.run(["ollama", "create", name, "-f", modelfile], check=True)
    print(f"\nOK: modelo '{name}' criado no Ollama. Teste: ollama run {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--lora", default=LORA_DIR)
    ap.add_argument("--llamacpp", default=os.environ.get("LLAMACPP_DIR", ""))
    ap.add_argument("--name", default=OLLAMA_NAME)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.lora):
        raise SystemExit(f"não achei {args.lora} — rode train_lora.py antes")

    merge(args.base, args.lora, MERGED_DIR)
    if args.merge_only:
        print("--merge-only: parei aqui. Modelo em out/merged/")
        return
    if not args.llamacpp:
        raise SystemExit("passe --llamacpp C:\\caminho\\llama.cpp (ou defina LLAMACPP_DIR) "
                         "para converter e registrar no Ollama. Ou use --merge-only.")
    to_gguf(MERGED_DIR, GGUF_PATH, args.llamacpp)
    register(GGUF_PATH, MODELFILE, args.name)


if __name__ == "__main__":
    main()
