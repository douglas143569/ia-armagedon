Write-Host "ARMAGEDON - Gerenciador de Vozes TTS" -ForegroundColor Cyan
Write-Host "====================================`n" -ForegroundColor Cyan

Write-Host "Vozes Disponíveis Atualmente:`n" -ForegroundColor Green

$python_code = @'
import pyttsx3

engine = pyttsx3.init()
voices = engine.getProperty("voices")

print(f"Total: {len(voices)} voz(es)\n")
for i, voice in enumerate(voices, 1):
    gender = "MASCULINO" if "male" in voice.name.lower() else "FEMININO" if "female" in voice.name.lower() else "INDEFINIDO"
    print(f"[{i}] {voice.name} ({gender})")
'@

python -c $python_code

Write-Host "`nComo adicionar mais vozes?" -ForegroundColor Cyan
Write-Host "============================"
Write-Host "1. Abra Configuracoes (Win + I)"
Write-Host "2. Vá para: Tempo e Idioma → Voz"
Write-Host "3. Clique em [+] para adicionar nova voz"
Write-Host "4. Selecione idioma e baixe"
Write-Host "5. Reinicie o ARMAGEDON`n"

Write-Host "Vozes Recomendadas:" -ForegroundColor Yellow
Write-Host "  - PT-BR: Masculino e Feminino"
Write-Host "  - EN-US: David (Masculino)"
Write-Host "  - ES: Masculino e Feminino"
Write-Host "  - FR: Masculino e Feminino`n"

Write-Host "Abrindo Configuracoes..." -ForegroundColor Green
Start-Sleep -Seconds 2
Start-Process "ms-settings:speech"
