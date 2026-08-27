@echo off
REM ARMAGEDON - Gerador de Imagens
REM Criado em 2026-08-27

echo.
echo ================================
echo  ARMAGEDON - Gerador de Imagens
echo ================================
echo.

REM Verificar se venv existe
if not exist "venv_images" (
    echo Ambiente Python nao encontrado!
    echo Execute primeiro: .\setup-images.ps1
    echo.
    pause
    exit /b 1
)

REM Ativar venv e executar gerador
cd /d "%~dp0"
call venv_images\Scripts\activate.bat
python image_generator.py

pause
