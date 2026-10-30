# Day 0 environment check for Windows (PowerShell).
# Verifies Docker, the GPU, Ollama and the two models, and pulls models if missing.
# Run from the repository root:  powershell -ExecutionPolicy Bypass -File scripts\check-env.ps1

$ErrorActionPreference = "Continue"
$ChatModel  = "qwen2.5:7b-instruct"
$EmbedModel = "nomic-embed-text"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "[ok]   $text" -ForegroundColor Green }
function Bad($text)  { Write-Host "[FAIL] $text" -ForegroundColor Red }

Step "Docker"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker version --format "{{.Server.Version}}" 2>$null | ForEach-Object { Ok "Docker engine $_" }
    if ($LASTEXITCODE -ne 0) { Bad "Docker is installed but the engine is not running. Start Docker Desktop." }
    docker compose version
} else { Bad "docker not found on PATH" }

Step "GPU"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
} else { Bad "nvidia-smi not found. Install the NVIDIA driver." }

Step "Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Bad "ollama not found on PATH"
    exit 1
}
ollama --version

try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 | Out-Null
    Ok "Ollama API answers on http://localhost:11434"
} catch {
    Bad "Ollama API does not answer. Start the Ollama app, then run this script again."
    exit 1
}

foreach ($model in @($ChatModel, $EmbedModel)) {
    $installed = (ollama list) -join "`n"
    $bare = $model.Split(":")[0]
    if ($installed -match [regex]::Escape($bare)) {
        Ok "model present: $model"
    } else {
        Write-Host "Pulling $model ..." -ForegroundColor Yellow
        ollama pull $model
    }
}

Step "Quick generation test (also loads the model into VRAM)"
ollama run $ChatModel "Reply with the single word: ready" --keepalive 2m
Write-Host "`nVRAM after loading the model:"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
ollama ps

Step "Reminder"
Write-Host "Containers reach Ollama at http://host.docker.internal:11434."
Write-Host "If the API health check says Ollama is unreachable, set the Windows environment variable"
Write-Host "OLLAMA_HOST=0.0.0.0 and restart Ollama (allow it through the firewall for private networks only)."
