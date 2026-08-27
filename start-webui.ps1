# ARMAGEDON — Iniciar Open WebUI
# Interface web tipo ChatGPT conectada ao Ollama local

Write-Host "================================" -ForegroundColor Cyan
Write-Host "ARMAGEDON — Open WebUI" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

Write-Host "🚀 Iniciando Open WebUI..." -ForegroundColor Yellow
Write-Host "Aguarde um momento..." -ForegroundColor Gray

# Verificar se Ollama está rodando
$ollamaPath = "C:\Users\$env:USERNAME\AppData\Local\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaPath) {
    Write-Host "✅ Ollama encontrado" -ForegroundColor Green
} else {
    Write-Host "⚠️  Ollama não encontrado - certifique-se que está rodando" -ForegroundColor Yellow
}

Write-Host ""

# Iniciar Open WebUI
try {
    open-webui serve
} catch {
    Write-Host "❌ Erro ao iniciar Open WebUI:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "`nTente instalar com: npm install -g open-webui" -ForegroundColor Yellow
}
