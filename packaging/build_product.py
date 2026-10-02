"""把程序、手册、模板、示例打包成可以直接发给买家的压缩包。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging"
STAGE = PKG / "产品包"
APP_NAME = "科研数据清洗工具箱"
ZIP_NAME = f"{APP_NAME}_v0.1.zip"

README_TXT = """\
科研数据清洗工具箱 v0.1
========================================

【第一步】把整个文件夹解压到桌面（不要直接在压缩包里运行）
【第二步】双击「科研数据清洗工具箱」文件夹里的 exe
【第三步】想先试一遍？点界面上的「载入示例数据并运行」

----------------------------------------
文件夹里有什么
----------------------------------------
科研数据清洗工具箱/     程序本体，双击里面的 exe 启动
使用手册.html           操作手册（双击用浏览器打开，图文说明）
论文方法学模板.docx     中英文方法学段落模板 + 敏感性分析表模板
示例数据.csv            企鹅形态数据（344 行），练习用
示例报告/               用示例数据跑出来的完整结果，先看这个了解输出长什么样

----------------------------------------
遇到问题
----------------------------------------
1. 第一次启动要等 3-8 秒，属于正常现象。
2. 如果 Windows 提示「已保护你的电脑」，点「更多信息」→「仍要运行」。
   程序没有购买数字签名证书（个人开发者常见），不是病毒。
3. 程序全程在你电脑本地运行，不联网、不上传任何数据，可以断网验证。
4. 详细说明和常见问题见「使用手册.html」。

----------------------------------------
许可与支持
----------------------------------------
内核基于开源项目 robustclean（MIT 协议），可自由使用。
本项目为个人开发，购买后永久使用，后续版本免费更新。
使用中遇到问题请通过购买渠道留言，我会回复。

感谢支持。
"""


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> int:
    dist = ROOT / "dist" / "CleanToolbox"
    if not (dist / "CleanToolbox.exe").exists():
        print("先运行 PyInstaller 打包，dist/CleanToolbox 不存在")
        return 1

    # 重新生成一次示例报告，确保和当前版本一致
    print("生成示例报告…")
    run([sys.executable, "-X", "utf8", "examples/demo_penguins.py"])

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    print("复制程序本体（约 195 MB，需要一会）…")
    shutil.copytree(dist, STAGE / APP_NAME)
    # Windows 下 exe 名字改成中文，方便买家识别
    old = STAGE / APP_NAME / "CleanToolbox.exe"
    new = STAGE / APP_NAME / f"{APP_NAME}.exe"
    if old.exists():
        old.rename(new)

    for src, dst in [
        (PKG / "使用手册.html", STAGE / "使用手册.html"),
        (PKG / "论文方法学模板.docx", STAGE / "论文方法学模板.docx"),
        (ROOT / "examples" / "data" / "penguins_size.csv", STAGE / "示例数据.csv"),
    ]:
        shutil.copy2(src, dst)

    shutil.copytree(ROOT / "output" / "penguins", STAGE / "示例报告")
    (STAGE / "使用说明.txt").write_text(README_TXT, encoding="utf-8-sig")

    print("压缩中…")
    zpath = PKG / ZIP_NAME
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in sorted(STAGE.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(STAGE))

    total = sum(f.stat().st_size for f in STAGE.rglob("*") if f.is_file())
    print(f"\n产品包目录：{STAGE}")
    print(f"  解压后大小：{total / 1024 / 1024:.0f} MB")
    print(f"压缩包：{zpath}")
    print(f"  上传用大小：{zpath.stat().st_size / 1024 / 1024:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
