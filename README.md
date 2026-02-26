# Quick Screenshot Tool (Windows)

A small Windows utility with:

- global hotkey to capture screen
- save screenshots to your chosen folder
- a local web UI for settings and preview

## Setup

```powershell
py -m pip install -r requirements.txt
```

## Run

```powershell
py app.py
```

On Windows, the app now hides the console window by default. To keep it visible for debugging:

```powershell
$env:SCREENSHOT_SHOW_CONSOLE=1; py app.py
```

Run fully in background (no browser auto-open):

```powershell
py app.py --background
```

Default UI URL:

`http://127.0.0.1:5123`

## Build EXE (one-click)

Install PyInstaller:

```powershell
py -m pip install pyinstaller
```

Build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Output:

`dist\QuickScreenshot.exe`

Double-click the EXE to run. It will keep listening for the global hotkey in background and the web page is used to change hotkey and screenshot save directory.

## Usage

1. Open the UI.
2. Set `Save directory` and `Hotkey`, then click `Save settings`.
3. Press your hotkey anywhere in Windows to capture.
4. Check `Recent screenshots` in the UI.

## Supported hotkey keys

- `A-Z`, `0-9`
- `F1-F24`
- `PrintScreen`, `Enter`, `Tab`, arrows
- Modifiers: `Ctrl`, `Alt`, `Shift`, `Win`

Example: `Ctrl+Shift+S`
