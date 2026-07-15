# GitHub Actions macOS App Build

The macOS app build is configured in:

```text
.github/workflows/build-macos-app.yml
```

Push to GitHub on `master` or `main`, then open:

```text
Actions -> Build macOS RPG app
```

When the workflow succeeds, download the artifact:

```text
RPG-macOS-app
```

It contains:

```text
RPG-macOS.zip
```

Unzip it to get:

```text
RPG.app
```
