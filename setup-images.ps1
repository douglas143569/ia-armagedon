# ARMAGEDON - Configurar Geração de Imagens
# Instala Stable Diffusion via Python

Write-Host "================================" -ForegroundColor Cyan
Write-Host "ARMAGEDON - Gerador de Imagens" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

# Verificar Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python nao encontrado!" -ForegroundColor Red
    Write-Host "   Instale em: https://www.python.org/" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Python encontrado`n" -ForegroundColor Green

# Criar venv para imagens
Write-Host "Criando ambiente Python..." -ForegroundColor Yellow
python -m venv venv_images

Write-Host "Ativando ambiente..." -ForegroundColor Yellow
& .\venv_images\Scripts\Activate.ps1

Write-Host "`nInstalando dependências..." -ForegroundColor Yellow
Write-Host "   - torch (PyTorch)" -ForegroundColor Gray
Write-Host "   - diffusers (Stable Diffusion)" -ForegroundColor Gray
Write-Host "   - transformers (modelos)" -ForegroundColor Gray
Write-Host "   - pillow (processamento de imagem)" -ForegroundColor Gray

pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -q diffusers transformers pillow accelerate

Write-Host "`n================================" -ForegroundColor Green
Write-Host "✅ Setup Concluido!" -ForegroundColor Green
Write-Host "================================`n" -ForegroundColor Green

Write-Host "Proximos passos:" -ForegroundColor Yellow
Write-Host "1. Abra PowerShell" -ForegroundColor Gray
Write-Host "2. Execute: venv_images\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "3. Execute: python image_generator.py" -ForegroundColor Gray

Write-Host "`nOu use o botao na interface ARMAGEDON!" -ForegroundColor Cyan
