# 🎬 Controlador de Vídeos - Guia Completo

**Data:** 2026-08-28  
**Versão:** ARMAGEDON v3 com Controlador Interativo

---

## 🎯 O que é Novo?

Agora você pode:
✅ **Controlar FPS** (1-30 frames por segundo)
✅ **Controlar Duração** (1-30 segundos)
✅ **Escolher Modo** (Camera, Frames, Evolução)
✅ **Escolher Modelo** (SD-Turbo ou SD-1.5)
✅ **Escolher Resolução** (384x384 ou 512x512)
✅ **Ver Tempo Estimado** em tempo real
✅ **Usar Presets** para configurações rápidas

---

## 🚀 Como Acessar

### Opção 1: Interface Web (Recomendado)

**Terminal:**
```bash
cd c:\Users\7700781010\Desktop\iadouglas\ia-armagedon
python video_generator_flask.py
```

**Navegador:**
```
http://localhost:5001/ui
```

### Opção 2: Diretamente via API

Qualquer cliente HTTP (curl, Postman, etc)

---

## 🎨 Interface Web - Como Usar

### 1️⃣ Duração (⏱️)
```
Slider: 1-30 segundos
Padrão: 4 segundos

Exemplos:
- 2 seg = vídeo muito curto
- 4 seg = vídeo normal (recomendado)
- 8 seg = vídeo mais longo
- 30 seg = vídeo muito longo
```

### 2️⃣ FPS (🎞️)
```
Slider: 1-30 frames/segundo
Padrão: 6 FPS

Exemplos:
- 4 FPS = animação travada (rápido)
- 6 FPS = animação normal (padrão)
- 12 FPS = animação suave
- 24 FPS = muito suave (lento)
```

**Impacto no Tempo:**
```
4 FPS + 4 seg + camera = ~40 segundos
6 FPS + 4 seg + camera = ~45 segundos
12 FPS + 4 seg + camera = ~60 segundos
```

### 3️⃣ Modo (🎨)

#### Camera (Recomendado)
```
- Gera 1 imagem
- Aplica efeito Ken Burns (zoom + pan)
- 10x mais rápido
- Melhor para: vídeos genéricos
```

#### Frames
```
- Gera múltiplos frames independentes
- Mais variedade visual
- Mais lento
- Melhor para: máxima criatividade
```

#### Evolução
```
- Começa com 1 imagem
- Evolui via img2img
- Animação mais coherente
- Melhor para: sequências temáticas
```

### 4️⃣ Modelo (🤖)

#### SD-Turbo (Padrão)
```
- 4 steps
- Muito rápido (~1-1.5 min)
- Qualidade boa
- Recomendado para a maioria
```

#### SD-1.5
```
- 20 steps
- Mais lento (~3-5 min)
- Qualidade excelente
- Para quando qualidade importa
```

### 5️⃣ Resolução (📐)

#### 384x384 (Rápido)
```
- Mais rápido
- Menos memória
- Qualidade aceitável
- Recomendado para testes
```

#### 512x512 (Padrão)
```
- Bom balanço
- Qualidade melhor
- Padrão recomendado
```

---

## ⚡ Presets Rápidos

### ⚡ Rápido (1 minuto)
```
- Duração: 2s
- FPS: 4
- Modo: Camera
- Modelo: SD-Turbo
- Resolução: 384x384
- Tempo: ~1 minuto
```

### 🎬 Médio (1.5 minutos)
```
- Duração: 4s
- FPS: 6
- Modo: Camera
- Modelo: SD-Turbo
- Resolução: 512x512
- Tempo: ~1.5 minutos
```

### ✨ Qualidade (3 minutos)
```
- Duração: 4s
- FPS: 8
- Modo: Frames
- Modelo: SD-1.5
- Resolução: 512x512
- Tempo: ~3 minutos
```

### 🎥 Cinema (5+ minutos)
```
- Duração: 8s
- FPS: 12
- Modo: Evolução
- Modelo: SD-1.5
- Resolução: 512x512
- Tempo: ~5+ minutos
```

---

## 📊 Estimativa de Tempo

A interface calcula o tempo automaticamente baseado em:

```
Base Time = (modo + modelo)
Adjusted = Base Time × (fps + duração)

Exemplo:
- Camera + SD-Turbo = 30s base
- +6 FPS, +4 seg = ~45-50s total
- Com overhead = ~60-70s ≈ 1.1 minutos
```

---

## 🎯 Exemplos Práticos

### Cenário 1: Teste Rápido
```
Duração: 2s
FPS: 4
Modo: Camera
Modelo: SD-Turbo
Resolução: 384x384

Prompt: "A sunset"
Tempo: ~1 minuto
```

### Cenário 2: Vídeo Normal
```
Duração: 4s
FPS: 6
Modo: Camera
Modelo: SD-Turbo
Resolução: 512x512

Prompt: "A futuristic robot with neon lights"
Tempo: ~1.5 minutos
```

### Cenário 3: Qualidade Alta
```
Duração: 6s
FPS: 8
Modo: Frames
Modelo: SD-1.5
Resolução: 512x512

Prompt: "A serene Japanese garden with cherry blossoms"
Tempo: ~3-4 minutos
```

### Cenário 4: Produção
```
Duração: 10s
FPS: 12
Modo: Evolução
Modelo: SD-1.5
Resolução: 512x512

Prompt: "A space station orbiting Earth, cinematic"
Tempo: ~6-8 minutos
```

---

## 📡 API REST

### Endpoint: `/estimate` (GET)

Calcula tempo estimado sem gerar vídeo:

```bash
curl -X POST http://localhost:5001/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "duration": 4,
    "fps": 6,
    "mode": "camera",
    "turbo": true,
    "size": 512
  }'
```

**Resposta:**
```json
{
  "estimated_seconds": 70,
  "estimated_minutes": 1.2,
  "frames": 24,
  "total_pixels": 3145728,
  "configuration": {
    "duration": 4,
    "fps": 6,
    "model": "turbo",
    "mode": "camera",
    "size": 512
  }
}
```

### Endpoint: `/generate` (POST)

Gera vídeo com seus parâmetros:

```bash
curl -X POST http://localhost:5001/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "um robô futurista",
    "duration": 4,
    "fps": 6,
    "mode": "camera",
    "turbo": true,
    "size": 512
  }'
```

### Endpoint: `/config` (GET)

Mostra limites e otimizações:

```bash
curl http://localhost:5001/config
```

**Resposta:**
```json
{
  "limits": {
    "max_fps": 30,
    "max_duration": 30,
    "min_duration": 1,
    "sizes": [384, 512]
  },
  "optimizations": {
    "float16": true,
    "quantization_int8": true,
    ...
  }
}
```

---

## 💡 Dicas Pro

✅ **Comece com Rápido** - teste a configuração  
✅ **Use Camera para testes** - 10x mais rápido  
✅ **Prompts específicos** - mais detalhes = melhor resultado  
✅ **Duração 4-6s é ideal** - não muito curto, não muito longo  
✅ **FPS 6-8 é ótimo** - balanço velocidade/suavidade  

❌ Não use FPS muito alto (>12) se quer rapidez  
❌ Não misture modes/modelos sem razão  
❌ Não gere vídeos muito longos (>20s) sem motivo  

---

## 🎨 Tipos de Prompt

### Bons Prompts (Rápidos)
```
"A sunset"
"A futuristic robot"
"A cozy cabin in snow"
"Neon city at night"
```

### Prompts Específicos (Melhores)
```
"A futuristic robot with glowing neon lights, detailed, cinematic"
"A serene Japanese garden with cherry blossoms, 4k, detailed"
"A cozy log cabin covered in snow with warm fireplace glow"
"A cyberpunk city street with rain and neon signs, cinematic"
```

---

## 🔧 Troubleshooting

### Estimativa não bate com o tempo real?
- A estimativa é aproximada
- Primeira execução pode ser mais lenta (carregamento)
- Depois fica mais rápido (modelo em cache)

### Quer mais velocidade?
- Reduza FPS
- Reduza duração
- Use modo Camera
- Use resolução 384x384
- Use SD-Turbo

### Quer melhor qualidade?
- Aumente FPS
- Use modo Frames
- Use SD-1.5
- Use resolução 512x512
- Aumente duração

---

## 📊 Referência Rápida

| Config | Tempo | Frames | Uso Ideal |
|--------|-------|--------|-----------|
| 2s + 4 FPS + Camera + Turbo | ~50s | 8 | Teste |
| 4s + 6 FPS + Camera + Turbo | ~70s | 24 | Normal |
| 4s + 8 FPS + Frames + SD1.5 | ~180s | 32 | Qualidade |
| 6s + 12 FPS + Evolucao + SD1.5 | ~300s | 72 | Cinema |

---

**Pronto para criar vídeos incríveis!** 🚀

Abra: **http://localhost:5001/ui**
