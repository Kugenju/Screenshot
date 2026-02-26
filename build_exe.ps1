param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PythonPath)) {
    throw "Python not found at: $PythonPath"
}

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "QuickScreenshot",
    "--add-data", "templates;templates",
    "--add-data", "static;static"
)

if ($Clean) {
    $args += "--clean"
}

$args += "app.py"

Write-Host "Building QuickScreenshot.exe ..."
& $PythonPath @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "  dist\\QuickScreenshot.exe"
