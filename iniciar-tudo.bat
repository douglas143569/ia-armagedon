@echo off
REM ARMAGEDON - Iniciar TUDO (Ollama + Interface)
REM Criado em 2026-08-27

echo.
echo ================================
echo  ARMAGEDON - Iniciando...
echo ================================
echo.

cd /d "%~dp0"

REM Iniciar Ollama em background
echo Iniciando Ollama...
start "ARMAGEDON - Ollama" ollama serve

REM Aguardar Ollama inicializar
timeout /t 5 /nobreak

REM Iniciar o Hub (server.js) em background
echo Iniciando Hub...
start "ARMAGEDON - Hub" node server.js

REM Aguardar o Hub subir
timeout /t 3 /nobreak

REM Abrir Interface no navegador
echo Abrindo interface...
start "" http://localhost:3000

echo.
echo ================================
echo  ARMAGEDON PRONTO!
echo ================================
echo.
echo - Ollama rodando em background
echo - Interface aberta no navegador
echo.
echo Mantenha esta janela aberta!
echo.

pause
