"""把截图里第三方悬浮条（屏幕右上角的「拖拽至此上传」）抹掉。

那块区域是窗口的纯色背景，用取色填充即可，不动任何界面元素。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SHOTS = Path(__file__).resolve().parent / "shots"
# 悬浮条大致覆盖的区域（窗口坐标）
BOX = (1040, 66, 1445, 236)


def clean(path: Path) -> None:
    with Image.open(path) as im:
        img = im.convert("RGB")
    # 从悬浮条左侧取背景色
    bg = img.getpixel((980, 130))
    draw = ImageDraw.Draw(img)
    draw.rectangle(BOX, fill=bg)
    img.save(path)
    print(f"cleaned {path.name}  bg=#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}")


def main() -> int:
    for name in ("main.png", "result.png"):
        p = SHOTS / name
        if p.exists():
            clean(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
