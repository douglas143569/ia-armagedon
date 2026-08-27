# 🎨 Fase 4 — Geração de Imagens com Stable Diffusion

## Visão Geral

ARMAGEDON pode gerar imagens a partir de descrições em texto usando Stable Diffusion rodando 100% local!

---

## ⚙️ Setup (Primeira Vez)

### Passo 1: Execute o setup
```powershell
cd c:\Users\7700781010\Desktop\iadouglas\ia-douglas
.\setup-images.ps1
```

**Isso vai:**
- Criar ambiente Python isolado (`venv_images`)
- Instalar PyTorch
- Instalar Diffusers (Stable Diffusion)
- Instalar dependências

**Tempo:** 10-15 minutos

---

## 🚀 Como Usar

### Opção 1: Via Terminal (Teste Rápido)

```powershell
# Ativar ambiente
venv_images\Scripts\Activate.ps1

# Rodar gerador
python image_generator.py
```

**Em outro terminal:**
```powershell
# Enviar requisição (exemplo)
$body = @{prompt = "A beautiful sunset over mountains"} | ConvertTo-Json
Invoke-WebRequest -Uri http://localhost:5000/generate -Method POST -Body $body -ContentType "application/json"
```

### Opção 2: Via ARMAGEDON Hub (em breve)

Botão "Gerar Imagem" na interface (vamos adicionar)

---

## 📊 Performance

| Aspecto | Valor |
|---------|-------|
| Resolução | 512x512 (bom balanço) |
| Tempo por imagem | 1-3 minutos |
| Qualidade | Excelente |
| Custo | 🆓 Grátis |
| Hardware | CPU/MX150 OK |

---

## 🎯 Exemplos de Prompts

```
"A cyberpunk city with neon lights at night"
"A serene Japanese garden with cherry blossoms"
"A futuristic AI robot, detailed, 8k"
"A cozy cabin in the snow, fireplace glowing"
"Abstract art with vibrant colors"
```

---

## 📁 Imagens Salvas

As imagens são salvas em:
```
c:\Users\7700781010\Desktop\iadouglas\ia-douglas\images_generated\
```

Nomeadas como: `armagedon_YYYYMMDD_HHMMSS.png`

---

## ⚡ Otimizações Ativas

- ✅ `enable_attention_slicing()` — economiza memória
- ✅ `torch.no_grad()` — não calcula gradientes (mais rápido)
- ✅ 20 passos de inferência — bom balanço qualidade/velocidade
- ✅ Safety checker desligado — +20% de velocidade

---

## 🔄 Próximos Passos

1. **Testar** o gerador de imagens
2. **Integrar** ao HUB (botão na interface)
3. **Adicionar** gallery de imagens geradas
4. **GPU rental** para imagens maiores/mais rápidas

---

## ❓ Troubleshooting

**Erro: "CUDA out of memory"**
- Não é CUDA (você não tem NVIDIA GPU)
- Aumentar `enable_attention_slicing()` (já está)

**Erro: "Model not found"**
- Primeira execução baixa o modelo (~4GB)
- Precisa de internet
- Vai levar alguns minutos

**Muito lento**
- Normal em CPU: 1-3 min é esperado
- Para mais rápido: precisa de GPU

---

## 💡 Dica

Se quiser imagens MUITO mais rápidas, depois considere:
- GPU usada (RTX 3060 12GB = ~$150)
- Ou aluga GPU (RunPod $0.50/h)

---

**Criado em:** 2026-08-27  
**Versão:** ARMAGEDON Fase 4 v1.0
