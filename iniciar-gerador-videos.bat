@echo off
REM ARMAGEDON - Gerador de Videos/GIFs (porta 5001)
REM Criado em 2026-08-27

echo.
echo ================================
echo  ARMAGEDON - Gerador de Videos
echo ================================
echo.

cd /d "%~dp0"

REM Verificar se venv existe
if not exist "venv_images" (
    echo Ambiente Python nao encontrado!
    echo Execute primeiro: .\setup-images.ps1
    echo.
    pause
    exit /b 1
)

echo AVISO: geracao de video em CPU e MUITO lenta nesta maquina.
echo Um GIF de 2s (12 frames) pode levar cerca de 1 hora.
echo.

REM Ativar venv e executar gerador
call venv_images\Scripts\activate.bat
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
python video_generator_flask.py

pause
