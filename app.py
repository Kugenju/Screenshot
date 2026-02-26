import argparse
import atexit
import json
import os
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from screenshot_service import ScreenshotService

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "save_dir": str(Path.home() / "Pictures" / "QuickShots"),
    "hotkey": "Ctrl+Shift+S",
}


def maybe_hide_console_window():
    if os.name != "nt":
        return
    if os.environ.get("SCREENSHOT_SHOW_CONSOLE", "").strip().lower() in {"1", "true", "yes"}:
        return

    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        # Keep startup resilient if Win32 APIs are unavailable.
        return


maybe_hide_console_window()


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CONFIG.copy()

    config = DEFAULT_CONFIG.copy()
    if isinstance(data, dict):
        if isinstance(data.get("save_dir"), str):
            config["save_dir"] = data["save_dir"]
        if isinstance(data.get("hotkey"), str):
            config["hotkey"] = data["hotkey"]
    return config


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


config = load_config()
service = ScreenshotService(config["save_dir"], config["hotkey"])
app = Flask(__name__)


@atexit.register
def shutdown_service():
    service.stop()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def get_config():
    return jsonify(
        {
            "save_dir": str(service.save_dir),
            "hotkey": service.hotkey_display,
        }
    )


@app.post("/api/config")
def update_config():
    payload = request.get_json(silent=True) or {}
    save_dir = payload.get("save_dir")
    hotkey = payload.get("hotkey")
    if not isinstance(save_dir, str) or not save_dir.strip():
        return jsonify({"error": "save_dir is required"}), 400
    if not isinstance(hotkey, str) or not hotkey.strip():
        return jsonify({"error": "hotkey is required"}), 400

    try:
        service.update_settings(save_dir=save_dir, hotkey=hotkey)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except OSError as exc:
        return jsonify({"error": f"Failed to update settings: {exc}"}), 500

    new_config = {"save_dir": str(service.save_dir), "hotkey": service.hotkey_display}
    save_config(new_config)
    return jsonify(new_config)


@app.post("/api/capture")
def capture():
    try:
        path = service.capture_screenshot()
    except OSError as exc:
        return jsonify({"error": f"Capture failed: {exc}"}), 500

    return jsonify(
        {
            "filename": path.name,
            "path": str(path),
            "url": f"/shots/{path.name}",
        }
    )


@app.get("/api/screenshots")
def list_screenshots():
    items = service.list_screenshots(limit=80)
    return jsonify(items)


@app.get("/shots/<path:filename>")
def serve_screenshot(filename):
    return send_from_directory(str(service.save_dir), filename)


def main():
    parser = argparse.ArgumentParser(description="Quick screenshot tool")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5123)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
