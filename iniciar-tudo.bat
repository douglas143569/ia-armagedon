@echo off
REM ARMAGEDON - Iniciar TUDO (Ollama + Interface)
REM Criado em 2026-08-27

echo.
echo ================================
echo  ARMAGEDON - Iniciando...
echo ================================
echo.

REM Iniciar Ollama em background
echo Iniciando Ollama...
start "ARMAGEDON - Ollama" ollama serve

REM Aguardar Ollama inicializar
timeout /t 5 /nobreak

REM Abrir Interface
echo Abrindo interface...
start "" "c:\Users\7700781010\Desktop\iadouglas\ia-douglas\interface.html"

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
