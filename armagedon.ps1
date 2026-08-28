# ============================================================================
#  ARMAGEDON - launcher unico + supervisor
#  Sobe todos os servicos na ordem, espera cada um ficar saudavel, abre o
#  navegador, e (por padrao) fica vigiando e reinicia o que cair.
#
#  Uso:
#    .\armagedon.ps1              sobe essenciais + gerador de imagens, e supervisiona
#    .\armagedon.ps1 -WithVideo   inclui o gerador de video (pesado)
#    .\armagedon.ps1 -Once        so inicia, nao fica supervisionando
#    .\armagedon.ps1 -NoBrowser   nao abre o navegador
#    .\armagedon.ps1 -Stop        mata hub/cerebro/geradores (deixa o Ollama)
# ============================================================================
param(
    [switch]$Stop,
    [switch]$WithVideo,
    [switch]$Once,
    [switch]$NoBrowser
)

$ErrorActionPreference = "SilentlyContinue"
$Root = $PSScriptRoot
$Py = Join-Path $Root "venv_images\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$MainLog = Join-Path $LogDir ("armagedon-" + (Get-Date -Format "yyyyMMdd") + ".log")

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $MainLog -Value $line
}

# --- definicao dos servicos -------------------------------------------------
$Services = @(
    @{ Name = "ollama"; Port = 11434; Health = "http://localhost:11434/api/version";
       Match = "ollama"; StartupSec = 20; Auto = $true
       Start = { Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden } }

    @{ Name = "cerebro"; Port = 5002; Health = "http://localhost:5002/health";
       Match = "armagedon_brain"; StartupSec = 45; Auto = $true
       Start = { Start-Process $Py -ArgumentList "armagedon_brain.py" -WorkingDirectory $Root -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $LogDir "cerebro.out.log") `
                    -RedirectStandardError  (Join-Path $LogDir "cerebro.err.log") } }

    @{ Name = "hub"; Port = 3000; Health = "http://localhost:3000/";
       Match = "server\.js"; StartupSec = 15; Auto = $true
       Start = { Start-Process "node" -ArgumentList "server.js" -WorkingDirectory $Root -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $LogDir "hub.out.log") `
                    -RedirectStandardError  (Join-Path $LogDir "hub.err.log") } }

    @{ Name = "imagem"; Port = 5000; Health = "http://localhost:5000/health";
       Match = "image_generator_final"; StartupSec = 180; Auto = $true
       Start = { Start-Process $Py -ArgumentList "image_generator_final.py" -WorkingDirectory $Root -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $LogDir "imagem.out.log") `
                    -RedirectStandardError  (Join-Path $LogDir "imagem.err.log") } }

    @{ Name = "video"; Port = 5001; Health = "http://localhost:5001/health";
       Match = "video_generator_flask"; StartupSec = 180; Auto = [bool]$WithVideo
       Start = { Start-Process $Py -ArgumentList "video_generator_flask.py" -WorkingDirectory $Root -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $LogDir "video.out.log") `
                    -RedirectStandardError  (Join-Path $LogDir "video.err.log") } }
)

function Test-Svc($svc) {
    try {
        $r = Invoke-WebRequest -Uri $svc.Health -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch { return $false }
}

function Kill-Svc($svc) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe' OR Name='ollama.exe'" |
        Where-Object { $_.CommandLine -match $svc.Match } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Log "  matei PID $($_.ProcessId) ($($svc.Name))" }
}

function Write-Status {
    $obj = [ordered]@{ atualizado = (Get-Date -Format "s") }
    foreach ($s in $Services) { $obj[$s.Name] = [bool](Test-Svc $s) }
    $obj | ConvertTo-Json -Compress | Set-Content -Path (Join-Path $LogDir "status.json") -Encoding utf8
}

# --- -Stop ----------------------------------------------------------------
if ($Stop) {
    Log "Parando ARMAGEDON (hub, cerebro, geradores)..."
    foreach ($s in $Services) { if ($s.Name -ne "ollama") { Kill-Svc $s } }
    Write-Status
    Log "Pronto. (Ollama foi deixado rodando.)"
    exit 0
}

# --- start ---------------------------------------------------------------
Log "==================== ARMAGEDON ===================="
if (-not (Test-Path $Py)) { Log "ERRO: venv_images nao encontrado. Rode o setup primeiro."; exit 1 }

foreach ($s in $Services) {
    if (-not $s.Auto) { Log "$($s.Name): pulado (use -WithVideo)"; continue }
    if (Test-Svc $s) { Log "$($s.Name): ja no ar (porta $($s.Port))"; continue }
    Log "$($s.Name): iniciando..."
    & $s.Start
    $deadline = (Get-Date).AddSeconds($s.StartupSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-Svc $s) { break }
    }
    if (Test-Svc $s) { Log "$($s.Name): OK (porta $($s.Port))" }
    else { Log "$($s.Name): NAO subiu em $($s.StartupSec)s - veja logs\$($s.Name).err.log" }
}
Write-Status

if (-not $NoBrowser) { Start-Process "http://localhost:3000" }

if ($Once) {
    Log "Servicos iniciados (-Once: sem supervisao). Feche quando quiser."
    exit 0
}

# --- supervisor --------------------------------------------------------------
Log "Supervisor ativo. Verifica a cada 15s e reinicia o que cair. Ctrl+C para parar (os servicos continuam)."
$lastRestart = @{}
while ($true) {
    Start-Sleep -Seconds 15
    foreach ($s in $Services) {
        if (-not $s.Auto) { continue }
        if (Test-Svc $s) { continue }
        $prev = $lastRestart[$s.Name]
        if ($prev -and ((Get-Date) - $prev).TotalSeconds -lt 60) { continue }  # backoff
        Log "$($s.Name): CAIU - reiniciando"
        Kill-Svc $s
        & $s.Start
        $lastRestart[$s.Name] = Get-Date
    }
    Write-Status
}
