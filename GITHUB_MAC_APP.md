# GitHub Actions macOS App Build

這個專案已加入 GitHub Actions workflow：

```text
.github/workflows/build-macos-app.yml
```

推到 GitHub 的 `main` 或 `master` 後，Actions 會在雲端 macOS runner 打包：

```text
RPG.app
```

完成後到 GitHub 專案的：

```text
Actions -> Build macOS RPG app -> 最新一次執行 -> Artifacts
```

下載：

```text
RPG-macOS-app
```

裡面會有：

```text
RPG-macOS.zip
```

解壓縮後就是 `RPG.app`。

也可以在 GitHub Actions 頁面手動按 `Run workflow` 重新打包。
