@echo off
REM ARMAGEDON - Iniciar Gerador de Videos com Interface de Controle
REM Data: 2026-08-28

echo.
echo ====================================================
echo  ARMAGEDON - Gerador de Videos (Interface Completa)
echo ====================================================
echo.

echo Iniciando servidor Python...
echo.

cd /d "%~dp0"

REM Iniciar servidor Flask
start "ARMAGEDON Video Generator" cmd /k python video_generator_flask.py

REM Aguardar servidor inicializar
echo Aguardando servidor inicializar (~30 segundos)...
timeout /t 5 /nobreak

REM Abrir interface no navegador
echo.
echo Abrindo interface no navegador...
start http://localhost:5001/ui

echo.
echo ====================================================
echo OK! Interface aberta em: http://localhost:5001/ui
echo ====================================================
echo.
echo Controle:
echo - FPS: 1-30 frames por segundo
echo - Duracao: 1-30 segundos
echo - Modo: Camera, Frames, Evolucao
echo - Modelo: SD-Turbo ou SD-1.5
echo.
echo Mantenha esta janela aberta enquanto usar.
echo Feche para parar o servidor.
echo.
pause
