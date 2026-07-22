# Ember Kingdom: The Lost Throne

Python + Arcade 製作的 2D RPG。主要入口是 `rpg.py`，執行與打包需要同時保留程式碼、`assets/` 素材，以及 `Localization/` 語系檔。

## 本機執行

建議使用 Python 3.12 或 3.13。

```powershell
python -m pip install -r requirements.txt
python rpg.py
```

如果使用 Python 3.14，請改用專案提供的安裝腳本：

```powershell
.\setup_game.ps1
python rpg.py
```

## GitHub 打包 App

GitHub Actions 設定在 `.github/workflows/build-rpg-app.yml`。

推送到 GitHub 後：

1. 打開 GitHub repository。
2. 進入 `Actions`。
3. 選擇 `Build RPG App`。
4. 手動執行 workflow，或推送到 `main` / `master` 自動執行。
5. 到 workflow 結果下載 artifacts：
   - `EmberKingdom-Windows`：Windows 可執行版本。
   - `EmberKingdom-macOS`：macOS `.app` 版本。

## 本機打包

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller pyinstaller-hooks-contrib
python -m PyInstaller --noconfirm --clean RPG.spec
```

Windows 輸出在 `dist/EmberKingdom`，主程式是 `EmberKingdom.exe`。macOS 會由 GitHub Actions 產生 `EmberKingdom.app`。

## 重要檔案

- `rpg.py`：遊戲入口。
- `RPG.spec`：PyInstaller 打包設定。
- `assets/`：圖片、音效、字型、UI 素材。
- `Localization/`：語系 JSON。
- `ui/`：UI 元件與版面。
- `scripts/validate_assets.py`：素材完整性檢查。
