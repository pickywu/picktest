# GitHub App Build

This repository builds the game with GitHub Actions and PyInstaller.

## Build in GitHub

1. Push the repository to GitHub.
2. Open the repository on GitHub.
3. Go to `Actions` -> `Build RPG App`.
4. Run the workflow manually, or wait for a push to `main`/`master` to trigger it.
5. Download the artifact:
   - `EmberKingdom-Windows` contains `EmberKingdom-Windows.zip`.
   - `EmberKingdom-macOS` contains `EmberKingdom-macOS.zip` with `EmberKingdom.app`.

## Local Run

```powershell
python -m pip install -r requirements.txt
python rpg.py
```

## Local Package

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller pyinstaller-hooks-contrib
python -m PyInstaller --noconfirm --clean RPG.spec
```

On Windows, the packaged app is written to `dist/EmberKingdom`.
On macOS in GitHub Actions, the packaged app is written to `dist/EmberKingdom.app`.

## Included Runtime Files

The PyInstaller spec bundles:

- `assets/` for images, fonts, audio, and UI files.
- `Localization/` for editable language JSON files.
- `zhconv` package data for Simplified Chinese conversion.
