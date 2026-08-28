@echo off
REM Substituido pelo launcher unico. Redireciona pra ele.
cd /d "%~dp0"
echo Agora e so usar o ARMAGEDON.bat (launcher unico + supervisor).
echo Chamando...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0armagedon.ps1" %*
pause
