# 專案整理與維護指南

## 唯一依據

遊戲行為以 `rpg.py` 為準，畫面與圖片路徑以 `rpg_drawing.py`、`ui/assets.py` 為準。文件不得另行發明遊戲內不存在的職業、事件、藥水或素材名稱。

## 保留的正式內容

```text
PythonProject/
├─ rpg.py
├─ rpg_drawing.py
├─ mage.py / paladin.py / rogue.py / warlock.py / warrior.py
├─ ui/
├─ assets/
│  ├─ audio/
│  ├─ backgrounds/ / effects/
│  ├─ characters/monsters/
│  ├─ characters/players/
│  ├─ fonts/
│  └─ ui/
├─ docs/
├─ scripts/validate_assets.py
├─ requirements.txt
└─ setup_game.ps1
```

`.venv/`、`.idea/`、`.git/` 與 `saves/` 分別屬於本機環境、IDE、版本控制與玩家存檔，不算遊戲素材，也不應被素材清理腳本碰觸。

## 不應放回正式專案的內容

- 生圖原始母圖、裁切中間檔與舊版本 archive。
- QA 截圖、contact sheet、測試輸出與臨時報告。
- 0 位元的 PNG、字體、ZIP 或 Python 檔。
- `new`、`final`、`v2`、`fixed` 等靠檔名區分版本的重複素材。
- 已沒有對應工作流程的建置說明。

若需要保存生成過程，應放在專案外；只有驗收通過的 runtime 檔案才能進入 `assets/`。

## Runtime 素材載入規則

- `assets/audio/` 是遊戲音效的唯一正式位置；`SoundManager` 與生成腳本必須使用同一路徑。
- 背景、角色、怪物與特效應由統一 resolver 依 canonical 分類或語意 ID 讀取。
- UI 呼叫端只能使用 `ui/assets.py` 的語意名稱與 resolver；生成批次目錄是實作細節，不得散落到場景程式。
- 生成批次、版本號與 vertical-slice 名稱不得成為 runtime API；代表性素材也必須映射到 canonical 路徑。
- 正式素材缺失時應直接報錯，禁止用另一張不相干圖片靜默頂替。

## 清理後狀態

- 248 張圖片均位於用途導向的 canonical 路徑，並與 `ASSET_MANIFEST.json` 一一對應。
- 29 個 WAV 統一放在 `assets/audio/`，生成器與 `SoundManager` 使用相同位置。
- 玩家素材形成 `2 sex × 4 race × 5 job × 2 pose` 的完整矩陣。
- 怪物素材形成 `6 rank × 3 type × 2 pose` 的完整矩陣。
- UI 僅保留一套 `assets/ui/` 樹，不再以生成批次或版本目錄區分。

## 每次補圖後的檢查

1. 檔名與路徑完全符合 manifest，大小寫也一致。
2. 圖片可正常解碼，檔案不可為 0 位元。
3. 透明素材必須為 RGBA，四角不可帶白底、黑底或棋盤格。
4. 不新增 manifest 以外的預覽圖到 `assets/`。
5. 執行 Python 編譯檢查，再啟動遊戲逐頁驗收。

生成途中可執行 `python scripts/validate_assets.py --allow-missing`；完整交付時改用不帶參數的 `python scripts/validate_assets.py`，任何缺圖或格式錯誤都會回傳失敗。
