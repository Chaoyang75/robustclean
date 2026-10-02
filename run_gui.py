"""打包入口：PyInstaller 用这个文件作为起点。

直接双击 exe 即可使用。
演示模式：CleanToolbox.exe --demo（自动载入示例数据并跑一遍）
"""

import sys

from robustclean.gui import main

if __name__ == "__main__":
    raise SystemExit(main("--demo" in sys.argv))
