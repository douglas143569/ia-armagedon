@echo off
REM ============================================================
REM  ARMAGEDON - clique aqui para ligar tudo
REM  (launcher unico + supervisor - ver armagedon.ps1)
REM ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0armagedon.ps1" %*
pause
