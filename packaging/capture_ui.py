"""启动打包好的程序并截取界面，用于生成操作手册里的插图。"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "CleanToolbox" / "CleanToolbox.exe"
OUT_DIR = ROOT / "packaging" / "shots"
TITLE = "科研数据清洗工具箱"

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def find_window(title: str) -> int:
    """按标题找窗口；找不到就枚举一遍。"""
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        return hwnd
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                if title in buf.value:
                    found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def capture(path: Path, hwnd: int) -> bool:
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.5)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    box = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=box)
    # 全黑说明抓不到画面（没有桌面会话）
    extrema = img.convert("L").getextrema()
    if extrema[1] == 0:
        return False
    img.save(path)
    return True


def shoot(tag: str, args: list[str], wait: float) -> bool:
    """启动程序、等待、截图、关闭。"""
    proc = subprocess.Popen([str(EXE)] + args, cwd=str(EXE.parent))
    hwnd = 0
    for _ in range(40):
        time.sleep(0.5)
        hwnd = find_window(TITLE)
        if hwnd:
            break
    if not hwnd:
        proc.kill()
        print(f"FAILED[{tag}]: 没找到窗口")
        return False
    time.sleep(wait)
    out = OUT_DIR / f"{tag}.png"
    ok = capture(out, hwnd)
    proc.kill()
    time.sleep(1)
    if ok:
        from PIL import Image
        with Image.open(out) as im:
            print(f"OK {out.name} {im.size[0]}x{im.size[1]} {out.stat().st_size / 1024:.0f} KB")
    else:
        print(f"FAILED[{tag}]: 截到黑屏")
    return ok


def main() -> int:
    if not EXE.exists():
        print(f"找不到程序：{EXE}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok1 = shoot("main", [], 4)
    ok2 = shoot("result", ["--demo"], 30)
    return 0 if (ok1 and ok2) else 2


if __name__ == "__main__":
    raise SystemExit(main())
