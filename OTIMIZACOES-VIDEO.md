# ⚡ Otimizações para Geração de Vídeos (3-4x mais rápido!)

## ✅ O que foi otimizado

### 1. **Float16 em vez de Float32**
- Reduz uso de memória pela metade
- ~30-40% mais rápido
- Qualidade praticamente igual

### 2. **Modo Camera por Padrão**
- Gera apenas **1 imagem** + efeito Ken Burns (zoom + pan)
- **10x mais rápido** que gerar múltiplos frames
- Resultado: animação suave com movimento de câmera

### 3. **SD-Turbo por Padrão**
- 4 steps em vez de 15-20
- **3-4x mais rápido**
- Qualidade aceitável para vídeos

### 4. **Interpolação FAST**
- Usa Image.FAST em vez de LANCZOS
- ~20% mais rápido na composição de frames

---

## 🎯 Tempo Esperado Agora

| Antes | Depois | Ganho |
|-------|--------|-------|
| ~7 min/vídeo | ~2 min/vídeo | **3.5x** ⚡ |

---

## 🚀 Como Usar

### Opção 1: Padrão (Modo Camera + SD-Turbo) — RECOMENDADO
```json
POST /generate
{
  "prompt": "uma paisagem montanhosa ao pôr do sol",
  "duration": 4,
  "fps": 6
}
```
**Tempo esperado:** 2-3 minutos

---

### Opção 2: Qualidade Máxima (SD-1.5 + Modo Frames)
```json
POST /generate
{
  "prompt": "uma paisagem montanhosa ao pôr do sol",
  "duration": 4,
  "fps": 6,
  "turbo": false,
  "mode": "frames"
}
```
**Tempo esperado:** 6-8 minutos
**Qualidade:** Melhor, frames mais variados

---

### Opção 3: Ultra Rápido (SD-Turbo + Modo Camera, Resolução Baixa)
```json
POST /generate
{
  "prompt": "um robô futurista",
  "duration": 2,
  "fps": 4,
  "size": 384,
  "turbo": true,
  "mode": "camera"
}
```
**Tempo esperado:** 1-1.5 minutos

---

## 📊 Parâmetros Detalhados

| Parâmetro | Padrão | Opções | Velocidade |
|-----------|--------|--------|-----------|
| `turbo` | `true` | true/false | true = 3-4x mais rápido |
| `mode` | `camera` | frames/camera/evolucao | camera = 1 imagem + zoom (mais rápido!) |
| `size` | `512` | 384/512 | 384 = mais rápido, qualidade OK |
| `duration` | `4` | 1-10 | menos = menos frames |
| `fps` | `6` | 1-30 | menos = menos frames |
| `steps` | null | 1-30 | menos = mais rápido (só com turbo=false) |

---

## 💡 Dicas Práticas

✅ **Para vídeos rápidos:** modo camera + turbo + 2 seg duração
✅ **Para vídeos bonitos:** modo frames + sd15 + 4 seg duração
✅ **Teste com prompts simples:** "a sunset, 4k"

---

## 🔄 Próximas Otimizações Possíveis

Se ainda quiser mais velocidade:

1. **Quantização (int8)** — economiza mais 30%
2. **GPU Local** — 20-30x mais rápido (~$150 GPU usada)
3. **GPU Rental** — <10s por vídeo (~$0.30/h)

---

**Criado em:** 2026-08-28  
**Versão:** ARMAGEDON v1.1-otimizado
