#Requires -Version 5.1
<#
.SYNOPSIS
    一步启动 LNAgent Web（最小前端页面 + 后端 API）。

.DESCRIPTION
    这是 LNAgent Web 的单进程启动脚本：同一个 Python 进程同时提供前端页面和后端 API。

.EXAMPLE
    pwsh -File scripts/start-web.ps1

.EXAMPLE
    pwsh -File scripts/start-web.ps1 -ListenHost 0.0.0.0 -Port 9000
#>

param(
    [Alias("Host")]
    [string]$ListenHost = $(if ($env:LNAGENT_WEB_HOST) { $env:LNAGENT_WEB_HOST } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:LNAGENT_WEB_PORT) { [int]$env:LNAGENT_WEB_PORT } else { 8000 }),
    [string]$ProjectsDir = $(if ($env:LNAGENT_PROJECTS_DIR) { $env:LNAGENT_PROJECTS_DIR } else { "" }),
    [string]$PythonBin = $(if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" })
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ProjectsDir)) {
    $ProjectsDir = Join-Path $ProjectRoot "projects"
}

if ([string]::IsNullOrWhiteSpace($env:API_KEY)) {
    Write-Error @"
未设置 API_KEY。
请先设置环境变量，例如：
  `$env:API_KEY = "your-api-key"
"@
    exit 1
}

$modelName = if ($env:MODEL) { $env:MODEL } else { "gpt-4o-mini" }

$pythonCmd = Get-Command $PythonBin -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "未找到 Python 可执行文件: $PythonBin"
    exit 1
}

if (-not (Test-Path $ProjectsDir)) {
    New-Item -ItemType Directory -Path $ProjectsDir -Force | Out-Null
}

$env:MODEL = $modelName
$env:LNAGENT_PROJECTS_DIR = $ProjectsDir
$env:LNAGENT_WEB_HOST = $ListenHost
$env:LNAGENT_WEB_PORT = "$Port"

Set-Location $ProjectRoot

Write-Host "==> 启动 LNAgent Web" -ForegroundColor Cyan
Write-Host "项目目录: $ProjectRoot"
Write-Host "Python: $(& $PythonBin --version 2>&1)"
Write-Host "监听地址: http://$ListenHost`:$Port"
Write-Host "小说项目目录: $ProjectsDir"
Write-Host "前端页面: http://$ListenHost`:$Port/"
Write-Host "后端 API: http://$ListenHost`:$Port/api/projects"
Write-Host ""

& $PythonBin web_main.py --host $ListenHost --port $Port
exit $LASTEXITCODE
