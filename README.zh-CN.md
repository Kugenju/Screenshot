# Quick Screenshot 工具（Windows）

一个轻量的 Windows 截图工具，支持：

- 全局快捷键截图
- 自定义截图保存目录
- 独立桌面设置窗口（非浏览器）
- 系统托盘运行（最小化到托盘，后台持续监听）

## 安装依赖

```powershell
py -m pip install -r requirements.txt
```

## 运行

```powershell
py app.py
```

启动后直接隐藏到系统托盘：

```powershell
py app.py --background
```

Windows 下默认隐藏控制台黑框。如需调试显示控制台：

```powershell
$env:SCREENSHOT_SHOW_CONSOLE=1; py app.py
```

## 一键打包 EXE

先安装 PyInstaller：

```powershell
py -m pip install pyinstaller
```

执行打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

产物：

`dist\QuickScreenshot.exe`

双击 EXE 运行后，会显示独立窗口；最小化或关闭窗口后会进入系统托盘并继续后台运行。

## 使用说明

1. 打开应用窗口。
2. 设置 `Save folder` 和 `Hotkey`，点击 `Save Settings` 保存。
3. 在系统任意位置按快捷键触发截图。
4. 最小化或关闭窗口后，应用会进入托盘继续运行。
5. 可通过托盘菜单执行：打开设置、立即截图、退出应用。

## 支持的快捷键按键

- `A-Z`, `0-9`
- `F1-F24`
- `PrintScreen`, `Enter`, `Tab`, 方向键
- 修饰键：`Ctrl`, `Alt`, `Shift`, `Win`

示例：`Ctrl+Shift+S`
