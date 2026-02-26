from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
import time
from typing import Callable, List, Optional

import mss
import mss.tools
from pynput import keyboard

SPECIAL_KEYS = {
    "enter",
    "tab",
    "space",
    "backspace",
    "delete",
    "esc",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "insert",
    "page_up",
    "page_down",
    "print_screen",
}


class ScreenshotService:
    def __init__(self, save_dir: str, hotkey: str):
        self._listener = None
        self._state_lock = Lock()
        self._on_capture: Optional[Callable[[Path], None]] = None
        self.save_dir = Path(save_dir).expanduser()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.hotkey, self.hotkey_display = self._normalize_hotkey(hotkey)
        self._start_listener()

    def _start_listener(self):
        mapping = {self.hotkey: self._capture_callback}
        listener = keyboard.GlobalHotKeys(mapping)
        listener.start()
        self._listener = listener

    def _stop_listener(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def stop(self):
        with self._state_lock:
            self._stop_listener()

    def update_settings(self, save_dir: str, hotkey: str):
        normalized_hotkey, display_hotkey = self._normalize_hotkey(hotkey)
        target_dir = Path(save_dir).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)

        with self._state_lock:
            self._stop_listener()
            self.save_dir = target_dir
            self.hotkey = normalized_hotkey
            self.hotkey_display = display_hotkey
            self._start_listener()

    def set_on_capture(self, callback: Optional[Callable[[Path], None]]):
        with self._state_lock:
            self._on_capture = callback

    def _capture_callback(self):
        try:
            # Tiny delay helps avoid capturing the just-triggered foreground window.
            self.capture_screenshot(delay_seconds=0.2)
        except OSError:
            # Keep background listener alive if saving fails once.
            return

    def capture_screenshot(self, delay_seconds: float = 0.0) -> Path:
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        with self._state_lock:
            target_dir = self.save_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = datetime.now().strftime("shot_%Y%m%d_%H%M%S_%f.png")
        path = target_dir / filename

        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            mss.tools.to_png(shot.rgb, shot.size, output=str(path))

        self._play_capture_sound()
        self._notify_capture(path)
        return path

    def _notify_capture(self, path: Path):
        callback = None
        with self._state_lock:
            callback = self._on_capture
        if callback is None:
            return
        try:
            callback(path)
        except Exception:
            return

    @staticmethod
    def _play_capture_sound():
        try:
            import winsound

            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            return

    def list_screenshots(self, limit: int = 80) -> List[dict]:
        with self._state_lock:
            target_dir = self.save_dir

        if not target_dir.exists():
            return []

        files = [
            p
            for p in target_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        output = []
        for file in files[:limit]:
            output.append(
                {
                    "filename": file.name,
                    "size": file.stat().st_size,
                    "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
                    "url": f"/shots/{file.name}",
                }
            )
        return output

    @staticmethod
    def _normalize_hotkey(hotkey: str) -> tuple[str, str]:
        if not isinstance(hotkey, str):
            raise ValueError("Hotkey must be a string")

        clean = hotkey.strip().lower().replace(" ", "")
        if not clean:
            raise ValueError("Hotkey cannot be empty")

        raw_parts = [p for p in clean.split("+") if p]
        if not raw_parts:
            raise ValueError("Hotkey format is invalid")

        modifiers = []
        key = None

        for part in raw_parts:
            part = part.strip("<>")
            mapped_modifier = _map_modifier(part)
            if mapped_modifier:
                if mapped_modifier not in modifiers:
                    modifiers.append(mapped_modifier)
                continue

            if key is not None:
                raise ValueError("Hotkey must include exactly one non-modifier key")
            key = _map_key(part)

        if key is None:
            raise ValueError("Hotkey requires one key, for example Ctrl+Shift+S")

        normalized = "+".join(modifiers + [key])
        display = _display_hotkey(modifiers, key)
        return normalized, display


def _map_modifier(token: str):
    if token in {"ctrl", "control"}:
        return "<ctrl>"
    if token in {"alt", "option"}:
        return "<alt>"
    if token in {"shift"}:
        return "<shift>"
    if token in {"cmd", "win", "windows", "super"}:
        return "<cmd>"
    return None


def _map_key(token: str):
    if len(token) == 1 and token.isprintable():
        return token

    if token in {"prtsc", "printscreen"}:
        return "<print_screen>"
    if token in SPECIAL_KEYS:
        return f"<{token}>"
    if token.startswith("f") and token[1:].isdigit():
        key_num = int(token[1:])
        if 1 <= key_num <= 24:
            return f"<f{key_num}>"

    raise ValueError(
        "Unsupported key. Use one key like A-Z, 0-9, F1-F24, PrintScreen, Enter."
    )


def _display_hotkey(modifiers: list[str], key: str):
    display_tokens = []
    for mod in modifiers:
        if mod == "<ctrl>":
            display_tokens.append("Ctrl")
        elif mod == "<alt>":
            display_tokens.append("Alt")
        elif mod == "<shift>":
            display_tokens.append("Shift")
        elif mod == "<cmd>":
            display_tokens.append("Win")

    if key.startswith("<") and key.endswith(">"):
        pretty_key = key.strip("<>")
        if pretty_key == "print_screen":
            display_tokens.append("PrintScreen")
        else:
            display_tokens.append(pretty_key.upper())
    else:
        display_tokens.append(key.upper())

    return "+".join(display_tokens)
