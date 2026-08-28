# 🚀 ARMAGEDON — Guia Rápido

## Iniciar o ARMAGEDON

### Opção A: Interface Web (Recomendado)
```bash
open-webui serve
```
Depois abra: **http://localhost:8000**

- Primeira vez: crie uma conta (user/senha)
- Selecione **armagedon** como modelo
- Pronto para conversar!

### Opção B: Terminal Direto
```bash
ollama run armagedon
```

Ou com pergunta única:
```bash
ollama run armagedon "Qual é a capital da França?"
```

---

## 📋 Modelos Disponíveis

```
🔹 armagedon:latest   — Seu assistente pessoal customizado (recomendado)
🔹 qwen2.5:7b         — Modelo base de uso geral
🔹 dolphin-llama3     — Modelo criativo sem censura
```

Trocar de modelo no Open WebUI é fácil - selecione no dropdown.

---

## ⚙️ Customizar o ARMAGEDON

Edite o arquivo `Modelfile`:
- System prompt (personalidade, especialidades)
- Parâmetros (temperature, top_p, etc.)

Depois recrie com:
```bash
ollama create armagedon -f Modelfile
```

---

## 🛠️ Próximos Passos

### Fase 2.5: Interface Desktop (Tauri)
- Criar hub central no Windows
- Iniciar com Windows (autostart)
- Extensão no VS Code

### Fase 3: Assistente de Voz
- Wake word detection
- STT (Speech to Text)
- TTS (Text to Speech)
- Comandos por voz

### Fase 2: RAG + Tool Calling
- Acesso a seus documentos
- Executar scripts
- Integração com Git/projetos

---

## 💾 Hardware da Máquina

```
CPU: AMD Ryzen 5 2400G (APU, 4c/8t, até 3.6GHz)
RAM: 16GB (~14GB utilizáveis)
GPU: AMD Radeon RX Vega 11 integrada (sem CUDA — inferência em CPU)
Disco: 386GB livre em C: (+ D: e E: com centenas de GB)

Status: ✅ OK para chat 3B–8B; imagem lenta (~7 min/img); vídeo só com GPU alugada
```

---

## 📞 Comandos Úteis Ollama

```bash
# Listar modelos
ollama list

# Ver logs/status
ollama serve

# Remover modelo
ollama rm qwen2.5:7b

# Pull novo modelo
ollama pull llama2:7b

# Executar modelo interativo
ollama run armagedon
```

---

## 🔗 Links Úteis

- **Ollama**: https://ollama.ai
- **Open WebUI**: https://github.com/open-webui/open-webui
- **Modelos disponíveis**: https://ollama.ai/library
- **Documentação Qwen2.5**: https://huggingface.co/Qwen/Qwen2.5-7B

---

**Criado em**: 2026-08-27  
**Versão**: ARMAGEDON v1.0
