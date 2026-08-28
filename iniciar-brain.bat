@echo off
REM ARMAGEDON - Cerebro: RAG (documentos) + Memoria de longo prazo (porta 5002)
REM Criado em 2026-08-28

echo.
echo ================================
echo  ARMAGEDON - Cerebro (RAG + Memoria)
echo ================================
echo.

cd /d "%~dp0"

if not exist "venv_images" (
    echo Ambiente Python nao encontrado!
    echo Execute primeiro: .\setup-images.ps1
    echo.
    pause
    exit /b 1
)

call venv_images\Scripts\activate.bat
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
python armagedon_brain.py

pause
