param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if ($RecreateVenv -and (Test-Path -LiteralPath ".\.venv")) {
    Remove-Item -LiteralPath ".\.venv" -Recurse -Force
}

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    py -3.14 -m venv .venv
}

$python = ".\.venv\Scripts\python.exe"

function Invoke-Pip {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PipArgs)

    & $python -m pip @PipArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip failed: $($PipArgs -join ' ')"
    }
}

$versionInfo = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Python version."
}

Invoke-Pip install --upgrade pip

if ($versionInfo -eq "3.14") {
    Invoke-Pip install --only-binary=:all: pycairo Pillow "pyglet~=2.1.5" "pytiled-parser~=2.2.9" "attrs>=18.2.0" "cffi>=2.0.0" "pymunk==7.3.0"
    Invoke-Pip install --no-deps "arcade==3.3.3"
} else {
    Invoke-Pip install -r requirements.txt
}

Write-Host ""
Write-Host "Game dependencies are installed. Run:"
Write-Host ".\.venv\Scripts\python.exe rpg.py"
