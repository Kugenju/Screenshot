import argparse
import atexit
import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import pystray
from PIL import Image, ImageDraw

from screenshot_service import ScreenshotService


def resolve_runtime_paths():
    if getattr(sys, "frozen", False):
        data_dir = Path(sys.executable).resolve().parent
        return data_dir
    return Path(__file__).resolve().parent


DATA_DIR = resolve_runtime_paths()
CONFIG_PATH = DATA_DIR / "config.json"

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
        return


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


def create_icon_image(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, size - 4, size - 4), radius=12, fill=(38, 64, 96, 255))
    draw.rectangle((12, 20, size - 12, size - 14), fill=(240, 244, 250, 255))
    draw.rectangle((18, 12, size - 18, 22), fill=(240, 244, 250, 255))
    lens_size = int(size * 0.22)
    lens_x = size // 2
    lens_y = int(size * 0.5)
    draw.ellipse(
        (lens_x - lens_size, lens_y - lens_size, lens_x + lens_size, lens_y + lens_size),
        fill=(75, 154, 243, 255),
    )
    draw.ellipse(
        (
            lens_x - lens_size // 2,
            lens_y - lens_size // 2,
            lens_x + lens_size // 2,
            lens_y + lens_size // 2,
        ),
        fill=(224, 241, 255, 255),
    )
    return img


class ScreenshotDesktopApp:
    def __init__(self, root: tk.Tk, service: ScreenshotService, start_hidden: bool):
        self.root = root
        self.service = service
        self._quitting = False
        self._tray_icon = None
        self._tray_thread = None

        self.save_dir_var = tk.StringVar(value=str(self.service.save_dir))
        self.hotkey_var = tk.StringVar(value=self.service.hotkey_display)
        self.status_var = tk.StringVar(
            value=f"Running. Hotkey: {self.service.hotkey_display}"
        )

        self._icon_image = create_icon_image()
        self._tk_icon = None
        self._apply_window_icon()

        self._build_ui()
        self._start_tray()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self._handle_minimize)

        if start_hidden:
            self.root.after(150, self.hide_to_tray)

    def _apply_window_icon(self):
        try:
            from PIL import ImageTk

            self._tk_icon = ImageTk.PhotoImage(self._icon_image.resize((64, 64)))
            self.root.iconphoto(True, self._tk_icon)
        except Exception:
            return

    def _build_ui(self):
        self.root.title("Quick Screenshot")
        self.root.geometry("560x280")
        self.root.minsize(560, 280)

        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.pack(fill="both", expand=True)

        title = tk.Label(
            frame, text="Quick Screenshot", font=("Segoe UI", 16, "bold")
        )
        title.pack(anchor="w")

        tip = tk.Label(
            frame,
            text="Minimize or close window to keep running in system tray.",
            fg="#506070",
            font=("Segoe UI", 10),
        )
        tip.pack(anchor="w", pady=(2, 16))

        form = tk.Frame(frame)
        form.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Save folder", font=("Segoe UI", 10)).grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 12)
        )
        tk.Entry(form, textvariable=self.save_dir_var, font=("Segoe UI", 10)).grid(
            row=0, column=1, sticky="ew", pady=(0, 12)
        )
        tk.Button(form, text="Browse...", command=self.choose_save_dir).grid(
            row=0, column=2, padx=(8, 0), pady=(0, 12)
        )

        tk.Label(form, text="Hotkey", font=("Segoe UI", 10)).grid(
            row=1, column=0, sticky="w", padx=(0, 12)
        )
        tk.Entry(form, textvariable=self.hotkey_var, font=("Segoe UI", 10)).grid(
            row=1, column=1, sticky="ew"
        )

        actions = tk.Frame(frame)
        actions.pack(fill="x", pady=(18, 0))

        tk.Button(actions, text="Save Settings", command=self.save_settings).pack(
            side="left"
        )
        tk.Button(actions, text="Take Screenshot", command=self.take_screenshot).pack(
            side="left", padx=(8, 0)
        )
        tk.Button(actions, text="Minimize to Tray", command=self.hide_to_tray).pack(
            side="left", padx=(8, 0)
        )

        status = tk.Label(
            frame,
            textvariable=self.status_var,
            fg="#334455",
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
        )
        status.pack(fill="x", pady=(16, 0))

    def choose_save_dir(self):
        selected = filedialog.askdirectory(initialdir=self.save_dir_var.get() or None)
        if selected:
            self.save_dir_var.set(selected)

    def save_settings(self):
        save_dir = self.save_dir_var.get().strip()
        hotkey = self.hotkey_var.get().strip()
        if not save_dir:
            messagebox.showerror("Invalid path", "Save folder cannot be empty.")
            return
        if not hotkey:
            messagebox.showerror("Invalid hotkey", "Hotkey cannot be empty.")
            return

        try:
            self.service.update_settings(save_dir=save_dir, hotkey=hotkey)
            config = {
                "save_dir": str(self.service.save_dir),
                "hotkey": self.service.hotkey_display,
            }
            save_config(config)
            self.hotkey_var.set(self.service.hotkey_display)
            self.save_dir_var.set(str(self.service.save_dir))
            self.status_var.set(
                f"Saved. Hotkey: {self.service.hotkey_display} | Folder: {self.service.save_dir}"
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("Failed to save settings", str(exc))

    def take_screenshot(self):
        self.status_var.set("Capturing screenshot...")
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self):
        try:
            path = self.service.capture_screenshot()
            self.root.after(
                0, lambda: self.status_var.set(f"Saved screenshot: {path.name}")
            )
        except OSError as exc:
            self.root.after(
                0, lambda: self.status_var.set(f"Capture failed: {exc}")
            )

    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open Settings", self._tray_open),
            pystray.MenuItem("Take Screenshot", self._tray_capture),
            pystray.MenuItem("Exit", self._tray_exit),
        )
        self._tray_icon = pystray.Icon(
            "QuickScreenshot",
            self._icon_image,
            "Quick Screenshot",
            menu,
        )
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _tray_open(self, icon, item):
        self.root.after(0, self.show_window)

    def _tray_capture(self, icon, item):
        self.root.after(0, self.take_screenshot)

    def _tray_exit(self, icon, item):
        self.root.after(0, self.quit_app)

    def _handle_minimize(self, event):
        if self._quitting:
            return
        if self.root.state() == "iconic":
            self.root.after(0, self.hide_to_tray)

    def show_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        if self._quitting:
            return
        self.root.withdraw()
        self.status_var.set(
            f"Running in tray. Hotkey: {self.service.hotkey_display}"
        )

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        if self._tray_icon is not None:
            self._tray_icon.stop()
        self.service.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Quick screenshot desktop tool")
    parser.add_argument(
        "--background",
        action="store_true",
        help="Start hidden in system tray",
    )
    args = parser.parse_args()

    config = load_config()
    service = ScreenshotService(config["save_dir"], config["hotkey"])

    @atexit.register
    def shutdown_service():
        service.stop()

    maybe_hide_console_window()
    root = tk.Tk()
    ScreenshotDesktopApp(root, service, start_hidden=args.background)
    root.mainloop()


if __name__ == "__main__":
    main()
