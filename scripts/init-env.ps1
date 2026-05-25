#Requires -Version 5.1
<#
.SYNOPSIS
    初始化 LNAgent 项目的 mamba 虚拟环境并安装依赖。

.DESCRIPTION
    1. 搜索 mamba 可执行文件
    2. 检查 LNAgent 环境是否存在，不存在则创建
    3. 激活环境并安装 requirements.txt 中的依赖

    Python 版本与现有 LNAgent 环境保持一致：3.12.13
#>

$ErrorActionPreference = "Stop"

$EnvName = "LNAgent"
$PythonVersion = "3.12.13"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

function Find-Mamba {
    $cmd = Get-Command mamba -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:USERPROFILE\.local\share\mamba\condabin\mamba.bat",
        "$env:USERPROFILE\miniforge3\condabin\mamba.bat",
        "$env:USERPROFILE\miniconda3\condabin\mamba.bat",
        "C:\ProgramData\miniforge3\condabin\mamba.bat",
        "D:\ProgramData\miniforge3\condabin\mamba.bat"
    )

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }

    return $null
}

function Test-MambaEnv {
    param(
        [string]$MambaExe,
        [string]$Name
    )

    $output = & $MambaExe env list 2>&1 | Out-String
    foreach ($line in ($output -split "`n")) {
        $trimmed = $line.Trim()
        if ($trimmed -match "^\s*$([regex]::Escape($Name))\s+") {
            return $true
        }
    }
    return $false
}

function Initialize-MambaShell {
    param([string]$MambaExe)

    $hook = & $MambaExe shell hook --shell powershell 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hook)) {
        throw "无法初始化 mamba shell hook"
    }
    Invoke-Expression $hook
}

Write-Host "==> LNAgent 环境初始化" -ForegroundColor Cyan
Write-Host "项目目录: $ProjectRoot"

$mambaExe = Find-Mamba
if (-not $mambaExe) {
    Write-Error @"
未找到 mamba。请先安装 Miniforge / Mambaforge，并确保 mamba 在 PATH 中。
参考: https://github.com/conda-forge/miniforge
"@
    exit 1
}

Write-Host "==> 找到 mamba: $mambaExe" -ForegroundColor Green
$mambaVersion = & $mambaExe --version 2>&1
Write-Host "    版本: $mambaVersion"

if (-not (Test-Path $RequirementsFile)) {
    Write-Error "未找到依赖文件: $RequirementsFile"
    exit 1
}

$envExists = Test-MambaEnv -MambaExe $mambaExe -Name $EnvName

if (-not $envExists) {
    Write-Host "==> 环境 '$EnvName' 不存在，正在创建 (Python $PythonVersion)..." -ForegroundColor Yellow

    & $mambaExe create -n $EnvName "python=$PythonVersion" -y

    if ($LASTEXITCODE -ne 0) {
        Write-Error "创建环境失败"
        exit 1
    }
    Write-Host "==> 环境创建完成" -ForegroundColor Green
} else {
    Write-Host "==> 环境 '$EnvName' 已存在，跳过创建" -ForegroundColor Green
}

Write-Host "==> 激活环境并安装依赖..." -ForegroundColor Cyan
Initialize-MambaShell -MambaExe $mambaExe

mamba activate $EnvName

if ($LASTEXITCODE -ne 0) {
    Write-Error "激活环境失败"
    exit 1
}

python --version
pip install -r $RequirementsFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "依赖安装失败"
    exit 1
}

Write-Host ""
Write-Host "==> 初始化完成！" -ForegroundColor Green
Write-Host "后续使用时请先激活环境:"
Write-Host "  mamba activate $EnvName"
Write-Host "然后运行: python main.py"
