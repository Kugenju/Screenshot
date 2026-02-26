import argparse
import atexit
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pystray
from PIL import Image, ImageDraw, ImageOps, ImageTk

from screenshot_service import ScreenshotService


def resolve_runtime_paths():
    if getattr(sys, "frozen", False):
        data_dir = Path(sys.executable).resolve().parent
        return data_dir
    return Path(__file__).resolve().parent


DATA_DIR = resolve_runtime_paths()
CONFIG_PATH = DATA_DIR / "config.json"
LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

DEFAULT_CONFIG = {
    "save_dir": str(Path.home() / "Pictures" / "QuickShots"),
    "hotkey": "Ctrl+Shift+S",
}

COLORS = {
    "bg": "#0E1628",
    "surface": "#131F35",
    "card": "#F8FAFF",
    "title": "#ECF2FF",
    "text": "#10233F",
    "muted": "#5A6C87",
    "accent": "#1D4ED8",
    "accent_hover": "#1E40AF",
    "secondary": "#E7EEFB",
    "secondary_hover": "#D9E4FA",
    "status": "#315079",
    "preview_bg": "#F8FBFF",
}

STATE_SHIFT = 0x0001
STATE_CTRL = 0x0004
STATE_ALT = 0x0008
STATE_SUPER_A = 0x0040
STATE_SUPER_B = 0x0080

MODIFIER_KEYSYMS = {
    "Shift_L",
    "Shift_R",
    "Control_L",
    "Control_R",
    "Alt_L",
    "Alt_R",
    "Meta_L",
    "Meta_R",
    "Super_L",
    "Super_R",
}

KEYSYM_TO_HOTKEY = {
    "Return": "Enter",
    "Tab": "Tab",
    "space": "Space",
    "BackSpace": "Backspace",
    "Delete": "Delete",
    "Escape": "Esc",
    "Up": "Up",
    "Down": "Down",
    "Left": "Left",
    "Right": "Right",
    "Home": "Home",
    "End": "End",
    "Insert": "Insert",
    "Prior": "Page_Up",
    "Next": "Page_Down",
    "Print": "PrintScreen",
    "Snapshot": "PrintScreen",
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


def enable_high_dpi_awareness():
    if os.name != "nt":
        return
    try:
        import ctypes

        # Prefer per-monitor v2 DPI awareness on modern Windows.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass

    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
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
    draw.rounded_rectangle((4, 4, size - 4, size - 4), radius=14, fill=(29, 78, 216, 255))
    draw.rounded_rectangle((12, 16, size - 12, size - 13), radius=8, fill=(241, 246, 255, 255))
    draw.rounded_rectangle((18, 12, size - 18, 22), radius=5, fill=(241, 246, 255, 255))
    lens_size = int(size * 0.20)
    lens_x = size // 2
    lens_y = int(size * 0.52)
    draw.ellipse(
        (lens_x - lens_size, lens_y - lens_size, lens_x + lens_size, lens_y + lens_size),
        fill=(64, 151, 255, 255),
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
        self._preview_window = None
        self._preview_img_label = None
        self._preview_name_label = None
        self._preview_meta_label = None
        self._preview_image_ref = None
        self._preview_hide_timer = None
        self._gallery_tree = None
        self._gallery_paths = {}
        self._gallery_thumbs = {}

        self.save_dir_var = tk.StringVar(value=str(self.service.save_dir))
        self.hotkey_var = tk.StringVar(value=self.service.hotkey_display)
        self.status_var = tk.StringVar(value=f"Ready. Hotkey: {self.service.hotkey_display}")

        self._icon_image = create_icon_image()
        self._tk_icon = None

        self._setup_style()
        self._apply_window_icon()
        self._build_ui()
        self._start_tray()
        self.refresh_screenshot_list()

        self.service.set_on_capture(self._on_capture)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self._handle_minimize)

        if start_hidden:
            self.root.after(200, self.hide_to_tray)

    def _setup_style(self):
        self.root.configure(bg=COLORS["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=COLORS["bg"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure(
            "Title.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["title"],
            font=("Segoe UI", 22, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=COLORS["bg"],
            foreground="#9BB2D6",
            font=("Segoe UI", 10),
        )
        style.configure(
            "CardTitle.TLabel",
            background=COLORS["card"],
            foreground=COLORS["text"],
            font=("Segoe UI", 12, "bold"),
        )
        style.configure(
            "Body.TLabel",
            background=COLORS["card"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Primary.TButton",
            background=COLORS["accent"],
            foreground="white",
            borderwidth=0,
            padding=(14, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", COLORS["accent_hover"]), ("pressed", COLORS["accent_hover"])],
        )
        style.configure(
            "Secondary.TButton",
            background=COLORS["secondary"],
            foreground=COLORS["text"],
            borderwidth=0,
            padding=(12, 8),
            font=("Segoe UI", 10),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", COLORS["secondary_hover"]), ("pressed", COLORS["secondary_hover"])],
        )
        style.configure(
            "App.TEntry",
            fieldbackground="white",
            foreground=COLORS["text"],
            bordercolor="#D7E1F2",
            lightcolor="#D7E1F2",
            darkcolor="#D7E1F2",
            insertcolor=COLORS["text"],
            padding=7,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Gallery.Treeview",
            font=("Segoe UI", 10),
            rowheight=76,
            background="white",
            fieldbackground="white",
            foreground=COLORS["text"],
            borderwidth=0,
        )
        style.configure(
            "Gallery.Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background="#EAF1FF",
            foreground=COLORS["text"],
            relief="flat",
        )
        style.map(
            "Gallery.Treeview",
            background=[("selected", "#DCEAFF")],
            foreground=[("selected", COLORS["text"])],
        )
        style.map(
            "Gallery.Treeview.Heading",
            background=[("active", "#DCEAFF")],
        )

    def _apply_window_icon(self):
        try:
            self._tk_icon = ImageTk.PhotoImage(self._icon_image.resize((64, 64), LANCZOS))
            self.root.iconphoto(True, self._tk_icon)
        except Exception:
            return

    def _build_ui(self):
        self.root.title("Quick Screenshot")
        self.root.geometry("920x640")
        self.root.minsize(860, 560)

        shell = ttk.Frame(self.root, style="App.TFrame", padding=(22, 18))
        shell.pack(fill="both", expand=True)

        ttk.Label(shell, text="Quick Screenshot", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="Beautiful desktop capture tool. Minimize to tray, keep working quietly.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 14))

        card = ttk.Frame(shell, style="Card.TFrame", padding=(18, 16))
        card.pack(fill="both", expand=True)
        card.grid_columnconfigure(1, weight=1)
        card.grid_rowconfigure(8, weight=1)

        ttk.Label(card, text="Settings", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            card,
            text="Choose screenshot folder and global hotkey.",
            style="Body.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 14))

        ttk.Label(card, text="Save folder", style="Body.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Entry(card, textvariable=self.save_dir_var, style="App.TEntry").grid(
            row=2, column=1, sticky="ew", pady=(0, 12)
        )
        ttk.Button(
            card, text="Browse", command=self.choose_save_dir, style="Secondary.TButton"
        ).grid(row=2, column=2, padx=(10, 0), pady=(0, 12))

        ttk.Label(card, text="Hotkey", style="Body.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Entry(card, textvariable=self.hotkey_var, style="App.TEntry").grid(
            row=3, column=1, sticky="ew"
        )
        ttk.Button(
            card,
            text="Record Keys",
            command=self.record_hotkey,
            style="Secondary.TButton",
        ).grid(row=3, column=2, padx=(10, 0))

        action_bar = ttk.Frame(card, style="Card.TFrame")
        action_bar.grid(row=4, column=0, columnspan=3, sticky="w", pady=(18, 8))

        ttk.Button(
            action_bar,
            text="Save Settings",
            command=self.save_settings,
            style="Primary.TButton",
        ).pack(side="left")
        ttk.Button(
            action_bar,
            text="Take Screenshot",
            command=self.take_screenshot,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            action_bar,
            text="Minimize to Tray",
            command=self.hide_to_tray,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))

        status_shell = tk.Frame(card, bg="#EEF3FF", bd=0, highlightthickness=1, highlightbackground="#D7E2FA")
        status_shell.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        status_shell.grid_columnconfigure(1, weight=1)
        dot = tk.Canvas(status_shell, width=12, height=12, bg="#EEF3FF", highlightthickness=0)
        dot.create_oval(2, 2, 10, 10, fill="#2E79FF", outline="")
        dot.grid(row=0, column=0, padx=(10, 8), pady=10)
        status_label = tk.Label(
            status_shell,
            textvariable=self.status_var,
            bg="#EEF3FF",
            fg=COLORS["status"],
            anchor="w",
            justify="left",
            font=("Segoe UI", 10),
        )
        status_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=10)

        ttk.Separator(card, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=(14, 12)
        )

        gallery_header = ttk.Frame(card, style="Card.TFrame")
        gallery_header.grid(row=7, column=0, columnspan=3, sticky="ew")
        gallery_header.grid_columnconfigure(1, weight=1)

        ttk.Label(gallery_header, text="Screenshots", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            gallery_header,
            text="Browse, open, and delete existing captures.",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        ttk.Button(
            gallery_header,
            text="Refresh",
            command=self.refresh_screenshot_list,
            style="Secondary.TButton",
        ).grid(row=0, column=2, rowspan=2, sticky="e")

        table_shell = tk.Frame(
            card,
            bg="white",
            highlightthickness=1,
            highlightbackground="#D7E2FA",
            bd=0,
        )
        table_shell.grid(row=8, column=0, columnspan=3, sticky="nsew")
        table_shell.grid_columnconfigure(0, weight=1)
        table_shell.grid_rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            table_shell,
            columns=("filename", "modified", "size"),
            show="tree headings",
            style="Gallery.Treeview",
        )
        tree.heading("#0", text="Preview")
        tree.column("#0", width=145, anchor="center", stretch=False)
        tree.heading("filename", text="Filename")
        tree.heading("modified", text="Modified")
        tree.heading("size", text="Size")
        tree.column("filename", width=360, anchor="w")
        tree.column("modified", width=185, anchor="w")
        tree.column("size", width=84, anchor="center", stretch=False)

        scroll_y = ttk.Scrollbar(table_shell, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll_y.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        tree.bind("<Double-1>", lambda _evt: self.open_selected_screenshot())
        tree.bind("<Delete>", lambda _evt: self.delete_selected_screenshot())
        self._gallery_tree = tree

        gallery_actions = ttk.Frame(card, style="Card.TFrame")
        gallery_actions.grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Button(
            gallery_actions,
            text="Open",
            command=self.open_selected_screenshot,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            gallery_actions,
            text="Delete",
            command=self.delete_selected_screenshot,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            gallery_actions,
            text="Open Folder",
            command=self.open_save_folder,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))

    def choose_save_dir(self):
        selected = filedialog.askdirectory(initialdir=self.save_dir_var.get() or None)
        if selected:
            self.save_dir_var.set(selected)

    def record_hotkey(self):
        hotkey = self._capture_hotkey_dialog()
        if not hotkey:
            return
        self.hotkey_var.set(hotkey)
        self.status_var.set(
            f"[{datetime.now():%H:%M:%S}] Captured hotkey: {hotkey}. Click Save Settings."
        )

    def _capture_hotkey_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Record Hotkey")
        dialog.configure(bg=COLORS["card"])
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        container = tk.Frame(dialog, bg=COLORS["card"], padx=16, pady=14)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text="Press your desired key combination",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        live_text = tk.StringVar(value="Waiting for keys...")
        tk.Label(
            container,
            textvariable=live_text,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            pady=10,
        ).pack(anchor="w")

        tk.Label(
            container,
            text="Tip: Press Esc without modifiers to cancel.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        result = {"value": None}
        active = {"closing": False}

        def close_dialog():
            if active["closing"]:
                return
            active["closing"] = True
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        def on_key_press(event):
            modifiers = self._modifiers_from_state(event.state)
            key = self._event_to_hotkey_key(event)

            if key is None:
                if modifiers:
                    live_text.set("+".join(modifiers) + " + ...")
                return "break"

            if key == "Esc" and not modifiers:
                close_dialog()
                return "break"

            tokens = modifiers + [key]
            hotkey = "+".join(tokens)
            live_text.set(f"Captured: {hotkey}")
            result["value"] = hotkey
            dialog.after(180, close_dialog)
            return "break"

        dialog.bind("<KeyPress>", on_key_press)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self._center_popup(dialog, width=380, height=130)
        dialog.focus_force()
        dialog.wait_window()
        return result["value"]

    @staticmethod
    def _modifiers_from_state(state):
        modifiers = []
        if state & STATE_CTRL:
            modifiers.append("Ctrl")
        if state & STATE_ALT:
            modifiers.append("Alt")
        if state & STATE_SHIFT:
            modifiers.append("Shift")
        if state & STATE_SUPER_A or state & STATE_SUPER_B:
            modifiers.append("Win")
        return modifiers

    @staticmethod
    def _event_to_hotkey_key(event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            return None
        if keysym in KEYSYM_TO_HOTKEY:
            return KEYSYM_TO_HOTKEY[keysym]
        if keysym.upper().startswith("F") and keysym[1:].isdigit():
            key_num = int(keysym[1:])
            if 1 <= key_num <= 24:
                return f"F{key_num}"
        if len(event.char) == 1 and event.char.isprintable():
            return event.char.upper()
        if len(keysym) == 1 and keysym.isprintable():
            return keysym.upper()
        return None

    def _center_popup(self, dialog: tk.Toplevel, width: int, height: int):
        dialog.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        x = root_x + max(0, (root_w - width) // 2)
        y = root_y + max(0, (root_h - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def refresh_screenshot_list(self, highlight_filename=None):
        if self._gallery_tree is None:
            return
        existing_selection = self._gallery_tree.selection()
        selected_name = None
        if existing_selection:
            selected_name = self._gallery_tree.set(existing_selection[0], "filename")

        self._gallery_tree.delete(*self._gallery_tree.get_children())
        self._gallery_paths.clear()
        self._gallery_thumbs.clear()

        items = self.service.list_screenshots(limit=300)
        target_iid = None
        for idx, item in enumerate(items):
            filename = item.get("filename", "")
            modified = self._format_modified(item.get("modified", ""))
            size_kb = max(1, int(item.get("size", 0) / 1024))
            iid = f"shot_{idx}"
            path = self.service.save_dir / filename
            thumb = self._build_gallery_thumbnail(path)
            self._gallery_tree.insert(
                "",
                "end",
                iid=iid,
                text="",
                image=thumb,
                values=(filename, modified, f"{size_kb} KB"),
            )
            self._gallery_paths[iid] = path
            self._gallery_thumbs[iid] = thumb
            if highlight_filename and filename == highlight_filename:
                target_iid = iid
            if not highlight_filename and selected_name and filename == selected_name:
                target_iid = iid

        if target_iid is None and self._gallery_tree.get_children():
            target_iid = self._gallery_tree.get_children()[0]

        if target_iid is not None:
            self._gallery_tree.selection_set(target_iid)
            self._gallery_tree.focus(target_iid)
            self._gallery_tree.see(target_iid)

    @staticmethod
    def _format_modified(modified_value):
        if not modified_value:
            return ""
        try:
            return datetime.fromisoformat(modified_value).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return str(modified_value)

    def _build_gallery_thumbnail(self, path: Path):
        size = (126, 72)
        try:
            with Image.open(path) as image:
                thumb = ImageOps.fit(image.convert("RGB"), size, method=LANCZOS)
            return ImageTk.PhotoImage(thumb)
        except Exception:
            fallback = Image.new("RGB", size, "#E8EFFC")
            draw = ImageDraw.Draw(fallback)
            draw.rectangle((10, 10, size[0] - 10, size[1] - 10), outline="#9DB4DF", width=2)
            draw.line((14, size[1] - 16, size[0] - 14, size[1] - 16), fill="#9DB4DF", width=2)
            draw.text((16, 24), "No Preview", fill="#5F78A8")
            return ImageTk.PhotoImage(fallback)

    def _selected_gallery_path(self):
        if self._gallery_tree is None:
            return None
        selected = self._gallery_tree.selection()
        if not selected:
            return None
        return self._gallery_paths.get(selected[0])

    def open_selected_screenshot(self):
        path = self._selected_gallery_path()
        if path is None:
            messagebox.showinfo("Select screenshot", "Please select one screenshot first.")
            return
        if not path.exists():
            messagebox.showwarning("Missing file", "The selected screenshot no longer exists.")
            self.refresh_screenshot_list()
            return
        self._open_path(path)

    def delete_selected_screenshot(self):
        path = self._selected_gallery_path()
        if path is None:
            messagebox.showinfo("Select screenshot", "Please select one screenshot first.")
            return
        if not path.exists():
            self.refresh_screenshot_list()
            return
        yes = messagebox.askyesno(
            "Delete screenshot",
            f"Delete this screenshot?\n\n{path.name}",
            parent=self.root,
        )
        if not yes:
            return
        try:
            path.unlink()
            self.status_var.set(f"[{datetime.now():%H:%M:%S}] Deleted: {path.name}")
            self.refresh_screenshot_list()
        except OSError as exc:
            messagebox.showerror("Delete failed", str(exc))

    def open_save_folder(self):
        folder = Path(self.service.save_dir)
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path(folder)

    def _open_path(self, target: Path):
        try:
            if os.name == "nt":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

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
            previous_dir = Path(self.service.save_dir)
            self.service.update_settings(save_dir=save_dir, hotkey=hotkey)
            config = {
                "save_dir": str(self.service.save_dir),
                "hotkey": self.service.hotkey_display,
            }
            save_config(config)
            self.hotkey_var.set(self.service.hotkey_display)
            self.save_dir_var.set(str(self.service.save_dir))
            if Path(self.service.save_dir) != previous_dir:
                self.refresh_screenshot_list()
            self.status_var.set(
                f"[{datetime.now():%H:%M:%S}] Settings saved. Hotkey: {self.service.hotkey_display}"
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("Failed to save settings", str(exc))

    def take_screenshot(self):
        self.status_var.set(f"[{datetime.now():%H:%M:%S}] Capturing screenshot...")
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self):
        try:
            self.service.capture_screenshot()
        except OSError as exc:
            self.root.after(
                0,
                lambda: self.status_var.set(f"[{datetime.now():%H:%M:%S}] Capture failed: {exc}"),
            )

    def _on_capture(self, path: Path):
        self.root.after(0, lambda p=path: self._on_capture_ui(p))

    def _on_capture_ui(self, path: Path):
        self.status_var.set(f"[{datetime.now():%H:%M:%S}] Saved screenshot: {path.name}")
        self.refresh_screenshot_list(highlight_filename=path.name)
        self._show_capture_preview(path)

    def _ensure_preview_window(self):
        if self._preview_window is not None and self._preview_window.winfo_exists():
            return

        window = tk.Toplevel(self.root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="#D4E3FF")

        box = tk.Frame(window, bg=COLORS["preview_bg"], bd=0, padx=10, pady=10)
        box.pack(fill="both", expand=True, padx=1, pady=1)

        self._preview_img_label = tk.Label(box, bg=COLORS["preview_bg"])
        self._preview_img_label.grid(row=0, column=0, rowspan=2, sticky="nsw")

        self._preview_name_label = tk.Label(
            box,
            text="",
            bg=COLORS["preview_bg"],
            fg=COLORS["text"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self._preview_name_label.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self._preview_meta_label = tk.Label(
            box,
            text="",
            bg=COLORS["preview_bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self._preview_meta_label.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))

        box.grid_columnconfigure(1, weight=1)
        self._preview_window = window

    def _show_capture_preview(self, path: Path):
        self._ensure_preview_window()
        if self._preview_window is None:
            return

        try:
            with Image.open(path) as image:
                thumb = ImageOps.fit(image.convert("RGB"), (150, 92), method=LANCZOS)
            self._preview_image_ref = ImageTk.PhotoImage(thumb)
            self._preview_img_label.configure(image=self._preview_image_ref, text="")
        except Exception:
            self._preview_img_label.configure(image="", text="(Preview unavailable)", fg=COLORS["muted"])

        file_kb = max(1, path.stat().st_size // 1024)
        self._preview_name_label.configure(text=path.name)
        self._preview_meta_label.configure(text=f"{file_kb} KB  |  Saved to {path.parent}")

        x, y = self._preview_position()
        self._preview_window.geometry(f"430x114+{x}+{y}")
        self._preview_window.deiconify()
        self._preview_window.lift()

        if self._preview_hide_timer is not None:
            self.root.after_cancel(self._preview_hide_timer)
        self._preview_hide_timer = self.root.after(2400, self._hide_capture_preview)

    def _preview_position(self):
        margin_x = 18
        margin_y = 50
        try:
            root_visible = self.root.state() != "withdrawn"
        except tk.TclError:
            root_visible = False

        if root_visible:
            self.root.update_idletasks()
            x = self.root.winfo_rootx() + margin_x
            y = self.root.winfo_rooty() + self.root.winfo_height() - 114 - margin_x
            return max(4, x), max(4, y)

        screen_h = self.root.winfo_screenheight()
        x = margin_x
        y = screen_h - 114 - margin_y
        return max(4, x), max(4, y)

    def _hide_capture_preview(self):
        self._preview_hide_timer = None
        if self._preview_window is not None and self._preview_window.winfo_exists():
            self._preview_window.withdraw()

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
        self.status_var.set(f"Running in tray. Hotkey: {self.service.hotkey_display}")

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        self.service.set_on_capture(None)
        self._hide_capture_preview()
        if self._preview_window is not None and self._preview_window.winfo_exists():
            self._preview_window.destroy()
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

    enable_high_dpi_awareness()
    maybe_hide_console_window()
    root = tk.Tk()
    ScreenshotDesktopApp(root, service, start_hidden=args.background)
    root.mainloop()


if __name__ == "__main__":
    main()
