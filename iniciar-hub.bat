@echo off
REM ARMAGEDON - Hub Server com Interface Grafica
REM Criado em 2026-08-27

echo.
echo ================================
echo  ARMAGEDON - HUB Server
echo ================================
echo.

REM Verificar se Node.js está instalado
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo Erro: Node.js nao encontrado!
    echo Instale em: https://nodejs.org/
    pause
    exit /b 1
)

REM Iniciar servidor
echo Iniciando servidor...
cd /d "%~dp0"
node server.js
