<#
.SYNOPSIS
    Automated launcher for Strix AI security pentesting and vulnerability scanning on EvalForge.
.DESCRIPTION
    Verifies Docker daemon status, LLM configuration, and Strix CLI presence, then executes
    a non-interactive, bounded automated security review against the codebase.
.PARAMETER ScanMode
    Scan depth mode: 'quick' (default, ~5-10m), 'standard' (~30m), or 'deep' (hours).
.PARAMETER MaxBudget
    Maximum USD LLM budget cap for the scan (default: 10).
.PARAMETER Target
    Target path or URL (default: './').
#>

param (
    [string]$ScanMode = "quick",
    [double]$MaxBudget = 10.0,
    [string]$Target = "./"
)

$ErrorActionPreference = "Continue"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "         EvalForge - Strix Security Runner       " -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verify Docker Daemon Status
Write-Host "[1/4] Checking Docker daemon status..." -ForegroundColor Yellow
$dockerCheck = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[X] ERROR: Docker is not running or unreachable." -ForegroundColor Red
    Write-Host "    Strix open-source CLI executes pentesting agents inside isolated OCI containers." -ForegroundColor DarkYellow
    Write-Host "    Action required:" -ForegroundColor DarkYellow
    Write-Host "      1. Launch Docker Desktop on Windows." -ForegroundColor White
    Write-Host "      2. Wait until Docker Desktop reports 'Engine running'." -ForegroundColor White
    Write-Host "      3. Re-run this script: .\scripts\run_strix_scan.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}
Write-Host "[+] Docker daemon is running." -ForegroundColor Green

# 2. Check for Strix executable
Write-Host "[2/4] Verifying Strix CLI installation..." -ForegroundColor Yellow
$strixCmd = Get-Command strix -ErrorAction SilentlyContinue
if (-not $strixCmd) {
    # Check known Python Scripts directories
    $userPyStrix = Get-ChildItem -Path "$env:LOCALAPPDATA\Python" -Filter "strix.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    $venvStrix = Join-Path $PSScriptRoot "..\services\worker\.venv\Scripts\strix.exe"

    if ($userPyStrix -and (Test-Path $userPyStrix)) {
        $strixBin = $userPyStrix
    } elseif (Test-Path $venvStrix) {
        $strixBin = $venvStrix
    } else {
        Write-Host "[!] Strix CLI not found in PATH. Attempting install via pip..." -ForegroundColor DarkYellow
        python -m pip install --quiet strix-agent
        $strixCmd = Get-Command strix -ErrorAction SilentlyContinue
        if ($strixCmd) {
            $strixBin = "strix"
        } else {
            Write-Host "[X] Failed to locate strix. Please run: pip install strix-agent" -ForegroundColor Red
            exit 1
        }
    }
} else {
    $strixBin = "strix"
}
Write-Host "[+] Strix binary ready: $strixBin" -ForegroundColor Green

# 3. Verify LLM configuration
Write-Host "[3/4] Checking AI provider configuration..." -ForegroundColor Yellow
if (-not $env:STRIX_LLM) {
    $env:STRIX_LLM = "openai/gpt-4o"
    Write-Host "[i] STRIX_LLM not specified. Defaulting to 'openai/gpt-4o'." -ForegroundColor DarkCyan
}

if (-not $env:LLM_API_KEY) {
    Write-Host ""
    Write-Host "[X] ERROR: LLM_API_KEY environment variable is not set." -ForegroundColor Red
    Write-Host "    Strix needs an API key to drive its security reasoning agents." -ForegroundColor DarkYellow
    Write-Host "    Please set your API key before running:" -ForegroundColor DarkYellow
    Write-Host "      `$env:STRIX_LLM = `"$($env:STRIX_LLM)`"" -ForegroundColor White
    Write-Host "      `$env:LLM_API_KEY = `"your-api-key-here`"" -ForegroundColor White
    Write-Host "      .\scripts\run_strix_scan.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}
Write-Host "[+] LLM configured: $($env:STRIX_LLM)" -ForegroundColor Green

# 4. Launch Scan
Write-Host "[4/4] Launching headless Strix security scan..." -ForegroundColor Yellow
Write-Host "      Target:     $Target" -ForegroundColor White
Write-Host "      Mode:       $ScanMode" -ForegroundColor White
Write-Host "      Max Budget: `$$MaxBudget USD" -ForegroundColor White
Write-Host ""

& $strixBin -n -t $Target --scan-mode $ScanMode --max-budget $MaxBudget

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[+] Security scan completed successfully!" -ForegroundColor Green
    Write-Host "    Inspect reports under: ./strix_runs/ (penetration_test_report.md, findings.sarif)" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "[!] Strix scan exited with status code $LASTEXITCODE." -ForegroundColor DarkYellow
}
