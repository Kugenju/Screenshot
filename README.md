# Quick Screenshot Tool (Windows)

A small Windows utility with:

- global hotkey to capture screen
- save screenshots to your chosen folder
- a native desktop settings window
- system tray support (minimize to tray, keep running in background)
- capture sound effect on every screenshot
- bottom-left preview popup after each capture
- screenshot gallery with thumbnails to view/open/delete captures
- hotkey recording by pressing keys directly
- optional auto-start at Windows login

## Setup

```powershell
py -m pip install -r requirements.txt
```

## Run

```powershell
py app.py
```

Start hidden in tray:

```powershell
py app.py --background
```

On Windows, the app hides console by default. To keep it visible for debugging:

```powershell
$env:SCREENSHOT_SHOW_CONSOLE=1; py app.py
```

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

Double-click the EXE to run. It opens a standalone app window and keeps running in system tray when minimized/closed.

## Usage

1. Open the app window.
2. Set `Save folder`, then use `Record Keys` or input `Hotkey` manually.
3. Toggle `Run at Windows startup` if you want auto-start on login.
4. Press your hotkey anywhere in Windows to capture.
5. The app plays a sound and shows a preview popup near the bottom-left after capture.
6. Manage existing screenshots in the centered thumbnail table (`Open`, `Delete`, `Rename`, `Open Folder`, `Refresh`).
7. Press `F2` on a selected screenshot to rename quickly.
8. Minimize or close the window to hide into tray and continue running.
9. Use tray icon menu to reopen settings, capture once, or exit.

## Supported hotkey keys

- `A-Z`, `0-9`
- `F1-F24`
- `PrintScreen`, `Enter`, `Tab`, arrows
- Modifiers: `Ctrl`, `Alt`, `Shift`, `Win`

Example: `Ctrl+Shift+S`
