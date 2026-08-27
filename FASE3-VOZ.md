# 🎤 Fase 3 — Assistente de Voz do ARMAGEDON

## O que foi instalado

```
✅ Whisper (OpenAI)        → STT (Speech to Text) - Voz para Texto
✅ Piper TTS               → TTS (Text to Speech) - Texto para Voz
✅ PyAudio                 → Captura de microfone
✅ openWakeWord (opcional) → Detecção de palavra de ativação
```

---

## Como Usar

### 1️⃣ Ativar o ambiente virtual

```powershell
cd c:\Users\7700781010\Desktop\iadouglas\ia-douglas
.\venv_voice\Scripts\Activate.ps1
```

### 2️⃣ Executar o assistente de voz

```powershell
python armagedon_voice.py
```

**O que acontece:**
1. Você fala no microfone (5 segundos)
2. Whisper transcreve seu áudio em português
3. ARMAGEDON processa a pergunta
4. Piper gera áudio da resposta
5. Áudio é reproduzido

### 3️⃣ Exemplos de uso

```bash
# Dentro do script interativo, você fala:
"Qual é a capital da França?"
"Me ajuda a escrever um script Python"
"O que você pode fazer por mim?"
```

---

## Componentes Detalhados

### 🎙️ Whisper (STT)

```bash
# Testar Whisper diretamente
whisper audio.mp3 --model base --language pt

# Modelos disponíveis: tiny, base, small, medium, large
# tiny: rápido mas menos preciso (~75MB)
# base: bom balanço (~140MB)
# small: mais preciso (~461MB)
```

**Comando no script:**
```python
result = whisper_model.transcribe("audio.wav", language="pt")
```

### 🔊 Piper TTS

```bash
# Testar Piper diretamente
echo "Olá Douglas" | piper --model pt_BR-faber-medium --output_file test.wav

# Modelos português:
# pt_BR-faber-medium   (recomendado - natural)
# pt_BR-edresson-medium (alternativa)
```

### 🎯 PyAudio (Microfone)

Captura áudio em tempo real:
```python
import pyaudio
import wave

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paFloat32, channels=1, 
                rate=16000, input=True)
data = stream.read(1024)
```

---

## Troubleshooting

### ❌ "PyAudio não funciona no Windows"

**Solução:**
```powershell
pip install pipwin
pipwin install pyaudio
```

### ❌ "Piper não encontrado"

**Instalar manualmente:**
```powershell
pip install piper-tts
# Download modelo:
piper --model pt_BR-faber-medium --update-models
```

### ❌ "Whisper muito lento"

**Use modelo menor:**
```python
whisper_model = whisper.load_model("tiny")  # Mais rápido
```

---

## Próximos Passos

### Fase 3.5: Wake Word Detection
```bash
pip install openwakeword
# Detectar "Oi ARMAGEDON" ou "OK ARMAGEDON"
```

### Fase 3.10: Automação Residencial
```bash
pip install home-assistant-api
# Comandar dispositivos via voz
# "Armagedon, liga a luz do escritório"
```

### Fase 4: Otimizações
- Usar GPU do MX150 pra Whisper (mais rápido)
- Cache de modelos Whisper
- Resposta em tempo real (streaming)

---

## Parâmetros Customizáveis

Edit `armagedon_voice.py`:

```python
# Duração da gravação (segundos)
audio_file = self.record_audio(duration=5)

# Modelo Whisper (tiny/base/small/medium/large)
voice = ARMAGEDONVoice(model_name="base")

# Idioma (pt/en/es/fr)
voice = ARMAGEDONVoice(language="pt")

# Número máximo de iterações
voice.interactive_loop(max_iterations=5)
```

---

## Hardware Usado

```
CPU: i7-8565U (processamento de Whisper)
GPU: MX150 (opcional - não otimizado ainda)
RAM: 34GB (Whisper usa ~500MB)
Latência: ~3-5s por ciclo (gravação + transcrição + LLM + TTS)
```

---

## Arquivo de Resposta

```
Arquivos gerados:
- input_0.wav, input_1.wav...  (seu áudio)
- output_0.wav, output_1.wav... (resposta do ARMAGEDON)
```

**Para limpar:**
```bash
rm input_*.wav output_*.wav
```

---

**Criado em:** 2026-08-27  
**Versão:** ARMAGEDON Fase 3 v1.0
