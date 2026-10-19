# ARMAGEDON - Script de Inicialização (PowerShell)

$projectPath = "c:\Users\7700781010\Desktop\iadouglas\ia-armagedon"
cd $projectPath

Write-Host "`n" -ForegroundColor Green
Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║     ARMAGEDON - Inicializador          ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# Matar processos antigos
Write-Host "🔄 Limpando processos antigos..." -ForegroundColor Yellow
Get-Process python, node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "✅ Processos antigos encerrados`n" -ForegroundColor Green

# Iniciar servidores
$servers = @(
    @{name="TTS (pyttsx3)"; cmd="python tts_generator.py"; port=5002},
    @{name="Imagem (Stable Diffusion)"; cmd="python image_generator_final.py"; port=5000},
    @{name="Vídeo (SD-Turbo)"; cmd="python video_generator_flask.py"; port=5001},
    @{name="Hub (Node.js)"; cmd="node server.js"; port=3000}
)

Write-Host "🚀 Iniciando servidores..." -ForegroundColor Cyan
Write-Host ""

foreach ($srv in $servers) {
    Write-Host "   ▶️  $($srv.name)..." -ForegroundColor White
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", "cd '$projectPath'; $($srv.cmd)" -WindowStyle Normal
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "⏳ Aguardando inicialização completa..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# Verificar se Hub está respondendo
Write-Host ""
Write-Host "🔍 Verificando Hub..." -ForegroundColor Cyan

$maxTries = 10
$tries = 0
$hubReady = $false

while ($tries -lt $maxTries -and -not $hubReady) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000/api/processes" -ErrorAction Stop -TimeoutSec 2
        $hubReady = $true
        Write-Host "✅ Hub respondendo!" -ForegroundColor Green
    } catch {
        $tries++
        Write-Host "   ⏳ Tentativa $tries/$maxTries..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

if ($hubReady) {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║  ✅ ARMAGEDON PRONTO!                 ║" -ForegroundColor Green
    Write-Host "║                                        ║" -ForegroundColor Green
    Write-Host "║  🌐 http://localhost:3000             ║" -ForegroundColor Green
    Write-Host "║  🔊 Clique em: Voz                   ║" -ForegroundColor Green
    Write-Host "║  👨 Teste: Gênero Masculino           ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""

    # Abrir navegador
    Write-Host "🌐 Abrindo navegador..." -ForegroundColor Cyan
    Start-Process "http://localhost:3000"
} else {
    Write-Host ""
    Write-Host "⚠️  Hub não respondeu após tentativas" -ForegroundColor Red
    Write-Host "💡 Verifique as janelas dos servidores para erros" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Feche esta janela quando terminar." -ForegroundColor Gray
Read-Host "Pressione Enter"
