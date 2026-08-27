# ╔════════════════════════════════════════════════════════╗
# ║  ARMAGEDON - Iniciar Tudo (Hub + Gerador de Imagens)   ║
# ╚════════════════════════════════════════════════════════╝

Write-Host "
╔════════════════════════════════════════════════════════╗
║          🔥 ARMAGEDON - INICIAR TUDO 🔥               ║
║  Hub (Node.js) + Gerador de Imagens (Python)          ║
╚════════════════════════════════════════════════════════╝
" -ForegroundColor Green

# Verificações
$nodeExists = node --version 2>$null
$pythonExists = python --version 2>$null

if (-not $nodeExists) {
    Write-Host "❌ Node.js não está instalado!" -ForegroundColor Red
    exit 1
}

if (-not $pythonExists) {
    Write-Host "❌ Python não está instalado!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Node.js: $nodeExists" -ForegroundColor Green
Write-Host "✅ Python: $pythonExists" -ForegroundColor Green
Write-Host ""

# Verificar se ambiente Python para imagens existe
if (-not (Test-Path "venv_images")) {
    Write-Host "⚠️  Ambiente venv_images não encontrado!" -ForegroundColor Yellow
    Write-Host "Execute primeiro: .\setup-images.ps1" -ForegroundColor Yellow
    Write-Host ""
}

# Terminal 1: Hub Server
Write-Host "📝 Terminal 1: Iniciando HUB Server (port 3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$PSScriptRoot'; node server.js`""

Start-Sleep -Seconds 2

# Terminal 2: Gerador de Imagens
if (Test-Path "venv_images") {
    Write-Host "📝 Terminal 2: Iniciando Gerador de Imagens (port 5000)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$PSScriptRoot'; .\venv_images\Scripts\Activate.ps1; python image_generator.py`""

    Start-Sleep -Seconds 2

    # Terminal 3: Abrir browser
    Write-Host "📝 Terminal 3: Abrindo HUB no browser..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "🌐 ARMAGEDON HUB: http://localhost:3000" -ForegroundColor Green
    Write-Host "🎨 Gerador de Imagens: http://localhost:5000" -ForegroundColor Green
    Write-Host ""

    Start-Sleep -Seconds 1
    Start-Process "http://localhost:3000"
} else {
    Write-Host "⚠️  Pulando Gerador de Imagens (execute setup-images.ps1 primeiro)" -ForegroundColor Yellow
    Start-Process "http://localhost:3000"
}

Write-Host "
✨ Tudo iniciado! Você pode usar ARMAGEDON normalmente:
   - Chat com IA (via Ollama)
   - Gerar imagens (botão 🎨 Imagem)
   - As imagens são salvas em: images_generated/

⏸️  Pressione Ctrl+C nos terminais para parar
" -ForegroundColor Green
