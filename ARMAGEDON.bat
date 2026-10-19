@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

cls
echo.
echo ################################
echo # ARMAGEDON - Sistema de IA    #
echo ################################
echo.

REM Matar processos antigos
echo Limpando processos antigos...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
timeout /t 2 /nobreak

cls
echo.
echo ################################
echo # ARMAGEDON - Iniciando        #
echo ################################
echo.

REM Iniciar TTS
echo [1/4] Iniciando Voz (TTS)...
start "ARMAGEDON - Voz" python tts_generator.py
timeout /t 2 /nobreak

REM Iniciar Imagem
echo [2/4] Iniciando Imagem...
start "ARMAGEDON - Imagem" python image_generator.py
timeout /t 2 /nobreak

REM Iniciar Video
echo [3/4] Iniciando Video...
start "ARMAGEDON - Video" python video_generator.py
timeout /t 2 /nobreak

REM Iniciar Hub
echo [4/4] Iniciando Hub...
start "ARMAGEDON - Hub" node server.js

echo.
echo Aguardando inicializacao... (20 segundos)
timeout /t 20 /nobreak

cls
echo.
echo ################################
echo #  ARMAGEDON PRONTO!           #
echo ################################
echo.
echo Abrindo navegador...
timeout /t 2 /nobreak

REM Abrir navegador
start http://localhost:3000

echo.
echo Sistema iniciado com sucesso!
echo.
pause
