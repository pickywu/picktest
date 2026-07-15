# RPG

Arcade + Pycairo desktop RPG.

## Run On Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_game.ps1
.\.venv\Scripts\python.exe rpg.py
```

## Run On macOS / Linux

```bash
chmod +x setup_game.sh
./setup_game.sh
./.venv/bin/python rpg.py
```

## Build macOS App

This repository uses GitHub Actions to build `RPG.app` on a cloud macOS runner.

After pushing to GitHub, open:

```text
Actions -> Build macOS RPG app
```

Download the `RPG-macOS-app` artifact. It contains `RPG-macOS.zip`, and the zip contains `RPG.app`.
