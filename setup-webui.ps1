# ARMAGEDON — Instalar Open WebUI (interface gráfica)
# Interface web local tipo ChatGPT rodando em localhost:8080

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Open WebUI Setup" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

Write-Host "Open WebUI é uma interface gráfica (tipo ChatGPT) que roda localmente." -ForegroundColor Gray
Write-Host "Ela se conecta ao Ollama e permite conversar facilmente.`n" -ForegroundColor Gray

Write-Host "Opção 1: Docker (recomendado - mais fácil)" -ForegroundColor Yellow
Write-Host "  docker run -d -p 8080:8080 --name open-webui ghcr.io/open-webui/open-webui:latest" -ForegroundColor Gray

Write-Host "`nOpção 2: npm/Node.js" -ForegroundColor Yellow
Write-Host "  npm install -g open-webui" -ForegroundColor Gray
Write-Host "  open-webui serve" -ForegroundColor Gray

Write-Host "`nOpção 3: Clone do GitHub (mais controle)" -ForegroundColor Yellow
Write-Host "  git clone https://github.com/open-webui/open-webui.git" -ForegroundColor Gray
Write-Host "  cd open-webui" -ForegroundColor Gray
Write-Host "  npm install" -ForegroundColor Gray
Write-Host "  npm run dev" -ForegroundColor Gray

Write-Host "`n================================" -ForegroundColor Green
Write-Host "✅ Uma vez instalado, abra: http://localhost:8080" -ForegroundColor Green
Write-Host "================================`n" -ForegroundColor Green

# Checar se Docker está instalado
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "✅ Docker encontrado! Você pode usar a Opção 1." -ForegroundColor Green
    Write-Host "`nPara iniciar Open WebUI com Docker:" -ForegroundColor Cyan
    Write-Host "  docker run -d -p 8080:8080 --name open-webui ghcr.io/open-webui/open-webui:latest`n" -ForegroundColor Gray
} else {
    Write-Host "⚠️  Docker não encontrado. Recomendado:" -ForegroundColor Yellow
    Write-Host "  https://www.docker.com/products/docker-desktop`n" -ForegroundColor Gray
}

# Checar se npm está instalado
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host "✅ npm encontrado! Você pode usar a Opção 2." -ForegroundColor Green
    Write-Host "`nPara iniciar com npm:" -ForegroundColor Cyan
    Write-Host "  npm install -g open-webui" -ForegroundColor Gray
    Write-Host "  open-webui serve`n" -ForegroundColor Gray
} else {
    Write-Host "⚠️  npm não encontrado. Para instalar:" -ForegroundColor Yellow
    Write-Host "  https://nodejs.org/`n" -ForegroundColor Gray
}

Write-Host "Dúvidas? Veja: https://github.com/open-webui/open-webui" -ForegroundColor Cyan
