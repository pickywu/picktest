餘燼王國 — 語系檔說明 / Localization Guide
====================================================

這個資料夾裡的每一個 .json 檔就是一個語言。玩家可以自由編輯、
新增語言。修改後重新啟動遊戲即可生效。
Each .json file here is one language. Edit or add freely; restart the game to
apply.

--------------------------------------------------
檔名 = 語系代碼 / File name = locale code
--------------------------------------------------
en.json  -> EN(英文)
ja.json  -> JA(日本語)
ko.json  -> KO(한국어)
zh-CN.json -> 簡體中文的「覆寫表」(見下)

繁體中文(zh-TW)是原文,不需要檔案。
Traditional Chinese (zh-TW) is the source language and needs no file.

--------------------------------------------------
檔案格式 / File format
--------------------------------------------------
標準 JSON 物件,「原文(繁體中文)」對應「翻譯」:

    {
        "開始遊戲": "ゲーム開始",
        "設定": "設定"
    }

規則 / Rules:
1. 左邊的「鍵(key)」是遊戲原文,請「不要修改」。只改右邊的翻譯值。
   Keys are the source text — do NOT change them. Translate the values only.
2. 帶有 {名稱} 的佔位符要原樣保留,例如:
   Keep {placeholders} intact, e.g.
       "恢復 {amount} 點血量。": "Restore {amount} HP."
3. 檔案必須是合法 JSON、UTF-8 編碼。壞掉的檔案會被略過並顯示警告,
   不會讓遊戲崩潰。
   Must be valid UTF-8 JSON. A broken file is skipped with a warning, never
   crashes the game.
4. 找不到的字串會自動回退為繁體中文原文(不會顯示成空白或亂碼)。
   Missing strings fall back to the Traditional-Chinese source.

--------------------------------------------------
新增一個語言 / Add a new language
--------------------------------------------------
1. 複製 en.json,改名成你的語系代碼,例如 fr.json、de.json、es.json。
   Copy en.json and rename it to your locale code (e.g. fr.json).
2. 把每個值翻成你的語言。
   Translate every value.
3. 重新啟動遊戲 → 標題右下角的語言選單就會出現這個新語言。
   Restart — the new language appears in the picker on the title screen.
   (畫面上的縮寫預設用檔名;若要漂亮的顯示名稱,可再調整。)

--------------------------------------------------
簡體中文 zh-CN.json(特例)/ Simplified Chinese
--------------------------------------------------
簡體中文是由繁體「自動轉換」而來,所以 zh-CN.json 預設是空的 {}。
只有當你想「覆寫」某個自動轉換結果時,才在這裡加對應,例如:
Simplified Chinese is auto-converted from Traditional, so zh-CN.json is empty by
default. Add an entry only to OVERRIDE a specific auto-conversion, e.g.

    {
        "某個原文": "你想要的簡體寫法"
    }

--------------------------------------------------
其他 / Notes
--------------------------------------------------
- en.phrases.json 是英文專用的「組合片語」進階檔,用來組出動態戰鬥文字。
  一般翻譯不需要動它;其他語言不使用這個機制。
  en.phrases.json is an advanced English-only helper for composing generated
  combat text. Other languages don't use it.
- 標題 / 勝利 / 死亡等「Logo」是圖片,不在這裡翻譯。
  Logos (title / VICTORY / DEATH) are images and are not translated here.
