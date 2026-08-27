@echo off
REM ARMAGEDON - Iniciar Web UI automaticamente
REM Criado em 2026-08-27

setlocal enabledelayedexpansion

echo.
echo ================================
echo  ARMAGEDON - Web UI
echo ================================
echo.

REM Esperar 3 segundos para iniciar Open WebUI
echo Iniciando Open WebUI...
timeout /t 2 /nobreak

REM Iniciar Open WebUI em background
start "" open-webui serve

REM Esperar Open WebUI inicializar
echo Aguardando inicializacao...
timeout /t 5 /nobreak

REM Abrir navegador automaticamente
echo Abrindo navegador...
start http://localhost:8000

echo.
echo ================================
echo  ARMAGEDON esta pronto!
echo  Abra: http://localhost:8000
echo ================================
echo.
echo Mantenha esta janela aberta enquanto usar.
echo Feche para parar ARMAGEDON.
echo.

pause
