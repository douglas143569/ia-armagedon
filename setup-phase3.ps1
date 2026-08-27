# ARMAGEDON — Fase 3: Assistente de Voz
# STT (Whisper) + TTS (Piper) + Wake Word Detection

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Fase 3 — Assistente de Voz" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

Write-Host "Componentes a instalar:" -ForegroundColor Yellow
Write-Host "  1. OpenAI Whisper (STT - voz → texto)" -ForegroundColor Gray
Write-Host "  2. Piper TTS (TTS - texto → voz em português)" -ForegroundColor Gray
Write-Host "  3. openWakeWord (detecção de ativação)" -ForegroundColor Gray
Write-Host "  4. PyAudio (captura de microfone)" -ForegroundColor Gray
Write-Host "`nTempo estimado: 10-15 minutos`n" -ForegroundColor Gray

# Verificar se Python está instalado
Write-Host "Verificando Python..." -ForegroundColor Yellow
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonVersion = python --version
    Write-Host "✅ Python encontrado: $pythonVersion`n" -ForegroundColor Green
} else {
    Write-Host "❌ Python não encontrado!" -ForegroundColor Red
    Write-Host "   Instale em: https://www.python.org/" -ForegroundColor Yellow
    exit 1
}

# Criar ambiente virtual
Write-Host "📦 Criando ambiente virtual Python..." -ForegroundColor Yellow
python -m venv venv_voice

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Ambiente virtual criado`n" -ForegroundColor Green
} else {
    Write-Host "❌ Erro ao criar ambiente virtual" -ForegroundColor Red
    exit 1
}

# Ativar ambiente virtual
Write-Host "Ativando ambiente virtual..." -ForegroundColor Yellow
& .\venv_voice\Scripts\Activate.ps1

# Instalar dependências
Write-Host "`n📥 Instalando dependências..." -ForegroundColor Yellow

Write-Host "   - openai-whisper (STT)..." -ForegroundColor Gray
pip install -q openai-whisper

Write-Host "   - piper-tts (TTS)..." -ForegroundColor Gray
pip install -q piper-tts

Write-Host "   - pyaudio (microfone)..." -ForegroundColor Gray
pip install -q pyaudio

Write-Host "   - openwakeword (wake word)..." -ForegroundColor Gray
pip install -q openwakeword

Write-Host "   - numpy, scipy (dependências)..." -ForegroundColor Gray
pip install -q numpy scipy

Write-Host "`n✅ Instalação concluída!`n" -ForegroundColor Green

Write-Host "================================" -ForegroundColor Green
Write-Host "Próximos passos:" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host "`n1. Testar Whisper (STT):" -ForegroundColor Yellow
Write-Host "   whisper --model base --language pt path/to/audio.mp3" -ForegroundColor Gray

Write-Host "`n2. Testar Piper (TTS):" -ForegroundColor Yellow
Write-Host "   echo 'Olá Douglas' | piper --model pt_BR-faber-medium --output_file test.wav" -ForegroundColor Gray

Write-Host "`n3. Script de voz em Python:" -ForegroundColor Yellow
Write-Host "   python armagedon_voice.py" -ForegroundColor Gray

Write-Host "`n[DICA] Ative o ambiente com: venv_voice\Scripts\Activate.ps1" -ForegroundColor Cyan
