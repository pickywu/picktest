$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
}

Write-Host "Installing Python 3.14 compatible game dependencies..."

# Arcade 3.3 pins Pymunk 6.9, which has no Windows wheel for Python 3.14.
# This game does not use Arcade's physics engine, so Pymunk 7 is safe here.
& $python -m pip install `
    "pymunk>=7.2,<8" `
    "pillow>=11.3,<12" `
    "pyglet>=2.1.5,<2.2" `
    "pytiled-parser>=2.2.9,<2.3" `
    "zhconv>=1.4"

& $python -m pip install --no-deps "arcade>=3.3,<4"

Write-Host "Done. Start the game with: .\.venv\Scripts\python.exe rpg.py"
