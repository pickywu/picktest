# Runtime assets

這個目錄只放遊戲執行時實際讀取的素材，不放提示詞、原圖、測試截圖或聯絡表。

正式 runtime 樹使用穩定用途名稱：

```text
assets/
├─ audio/                 # WAV 音效
├─ backgrounds/           # title/adventure/activities/battles/events/endings
├─ characters/
│  ├─ monsters/           # rank → pose → type
│  └─ players/tier_1/     # pose → sex → race → job
├─ effects/combat/        # 戰鬥特效
├─ fonts/                 # 可隨遊戲散佈的字體
└─ ui/                    # frames/meters/surfaces/scrollbars/slots/icons
```

程式與文件應引用這些 canonical 分類或語意資產 ID，不應依賴生成批次、版本號或 vertical-slice 目錄名稱。

目前 248 張圖片均登錄於 `../docs/ASSET_MANIFEST.json`，29 個音效統一位於 `audio/`。新增或重建素材時必須直接輸出到 manifest 指定的 canonical 路徑，不要另外建立 `final`、`new`、`v2` 或 `raw` 目錄。

字體缺少時程式會使用系統字體後備。
