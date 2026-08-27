# ARMAGEDON — Fase 1 Setup (Assistente de texto local)
# Script para baixar e testar modelos Ollama

Write-Host "================================" -ForegroundColor Cyan
Write-Host "ARMAGEDON — Fase 1 Setup" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

# Verificar se Ollama está instalado
Write-Host "Verificando Ollama..." -ForegroundColor Yellow
try {
    $version = ollama --version
    Write-Host "✅ Ollama encontrado: $version" -ForegroundColor Green
} catch {
    Write-Host "❌ Ollama não encontrado. Instale em: https://ollama.ai" -ForegroundColor Red
    exit 1
}

Write-Host "`nBaixando modelos recomendados..." -ForegroundColor Yellow
Write-Host "  1. Qwen2.5 7B (uso geral/dev)" -ForegroundColor Cyan
Write-Host "  2. Dolphin-Llama3 (criativo/uncensored)" -ForegroundColor Cyan
Write-Host "`nIsso pode levar 10-30 minutos dependendo da conexão...`n" -ForegroundColor Gray

# Baixar modelo geral
Write-Host "⬇️  Baixando Qwen2.5 7B..." -ForegroundColor Cyan
ollama pull qwen2.5:7b

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Qwen2.5 7B baixado com sucesso!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Qwen2.5 7B - falha no download" -ForegroundColor Yellow
}

# Baixar modelo uncensored/criativo
Write-Host "`n⬇️  Baixando Dolphin-Llama3..." -ForegroundColor Cyan
ollama pull dolphin-llama3:latest

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Dolphin-Llama3 baixado com sucesso!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Dolphin-Llama3 - falha no download" -ForegroundColor Yellow
}

# Listar modelos disponíveis
Write-Host "`n📦 Modelos disponíveis:" -ForegroundColor Cyan
ollama list

Write-Host "`n================================" -ForegroundColor Green
Write-Host "✅ Fase 1 concluída!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host "`nPróximos passos:" -ForegroundColor Yellow
Write-Host "  1. Testar modelos via terminal:"
Write-Host "     ollama run qwen2.5:7b"
Write-Host "     ollama run dolphin-llama3"
Write-Host "`n  2. Instalar Open WebUI (interface gráfica):"
Write-Host "     https://github.com/open-webui/open-webui"
Write-Host "`nPara conversar com ARMAGEDON via terminal:" -ForegroundColor Cyan
Write-Host "  ollama run qwen2.5:7b 'Qual é o seu nome?'" -ForegroundColor Gray
