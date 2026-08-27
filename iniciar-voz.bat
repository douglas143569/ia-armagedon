@echo off
REM ARMAGEDON - Assistente de Voz
REM Criado em 2026-08-27

setlocal enabledelayedexpansion

echo.
echo ================================
echo  ARMAGEDON - Assistente de Voz
echo ================================
echo.

cd /d "%~dp0"

REM Ativar ambiente virtual e executar script Python
call venv_voice\Scripts\activate.bat

echo Iniciando assistente de voz...
echo.

python armagedon_voice.py

pause
