# Demo: Teste da API de Geração de Vídeos
# Este é um exemplo de como usar quando o servidor estiver rodando

Write-Host "============================================================" -ForegroundColor Green
Write-Host "DEMO: Teste da API de Gerador de Vídeos Otimizado" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

# Exemplo 1: Gerar vídeo rápido
Write-Host "1️⃣  Exemplo: Gerar vídeo RÁPIDO (modo camera + SD-Turbo)" -ForegroundColor Cyan
Write-Host ""
$body = @{
    prompt = "um pôr do sol nas montanhas"
    duration = 4
    fps = 6
    turbo = $true
    mode = "camera"
    size = 512
} | ConvertTo-Json

Write-Host "Requisição:" -ForegroundColor Yellow
Write-Host "POST http://localhost:5001/generate"
Write-Host "Body:"
Write-Host $body -ForegroundColor White
Write-Host ""

Write-Host "Resposta esperada:" -ForegroundColor Yellow
Write-Host '{
  "job_id": "a1b2c3d4"
}' -ForegroundColor White
Write-Host ""

Write-Host "Tempo esperado: 1-1.5 minutos" -ForegroundColor Green
Write-Host ""

# Exemplo 2: Verificar status
Write-Host "2️⃣  Verificar status do vídeo:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Requisição:" -ForegroundColor Yellow
Write-Host "GET http://localhost:5001/status/a1b2c3d4"
Write-Host ""

Write-Host "Resposta esperada:" -ForegroundColor Yellow
Write-Host '{
  "status": "gerando",
  "percent": 45,
  "current": 15,
  "total": 30,
  "message": "Gerando imagem base...",
  "prompt": "um pôr do sol nas montanhas",
  "type": "vídeo",
  "model": "turbo",
  "mode": "camera"
}' -ForegroundColor White
Write-Host ""

# Exemplo 3: Listar todas as jobs
Write-Host "3️⃣  Listar todas as jobs:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Requisição:" -ForegroundColor Yellow
Write-Host "GET http://localhost:5001/jobs"
Write-Host ""

Write-Host "Resposta esperada:" -ForegroundColor Yellow
Write-Host '{
  "jobs": [
    {
      "id": "a1b2c3d4",
      "type": "vídeo",
      "prompt": "um pôr do sol nas montanhas",
      "model": "turbo",
      "mode": "camera",
      "status": "concluído",
      "percent": 100,
      "message": "Concluído!",
      "elapsed": 85,
      "active": false
    }
  ]
}' -ForegroundColor White
Write-Host ""

# Exemplo 4: Verificar configuração
Write-Host "4️⃣  Verificar otimizações ativas:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Requisição:" -ForegroundColor Yellow
Write-Host "GET http://localhost:5001/config"
Write-Host ""

Write-Host "Resposta esperada:" -ForegroundColor Yellow
Write-Host '{
  "optimizations": {
    "float16": true,
    "quantization_int8": true,
    "attention_slicing": true,
    "memory_efficient_attention": true,
    "default_model": "turbo",
    "default_mode": "camera",
    "preloaded": true
  },
  "performance": {
    "expected_time_per_video": "1-1.5 minutes",
    "speedup": "5-7x faster than baseline"
  }
}' -ForegroundColor White
Write-Host ""

Write-Host "============================================================" -ForegroundColor Green
Write-Host "Como testar?" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Terminal 1 - Iniciar servidor:" -ForegroundColor Yellow
Write-Host "cd c:\Users\7700781010\Desktop\iadouglas\ia-armagedon" -ForegroundColor White
Write-Host "python video_generator_flask.py" -ForegroundColor White
Write-Host ""
Write-Host "Terminal 2 - Fazer requisição:" -ForegroundColor Yellow
Write-Host 'Invoke-WebRequest -Uri "http://localhost:5001/generate" -Method POST -Body (ConvertTo-Json @{prompt="robot";duration=4;fps=6}) -ContentType "application/json"' -ForegroundColor White
Write-Host ""
