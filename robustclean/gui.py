"""图形界面：给不想碰命令行的用户用。

双击启动 → 选数据文件 → 点一个按钮 → 报告、图表、论文段落全部生成。
打包成 exe 后不需要安装 Python。
"""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "科研数据清洗工具箱"
APP_SUB = "九个检测器投票判定异常值 · 一键生成可用于论文的清洗报告"

FONT = ("Microsoft YaHei UI", 10)
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUB = ("Microsoft YaHei UI", 9)

STRATEGIES = [
    ("remove", "直接删除异常样本", "适合确认是测量错误的情况"),
    ("flag", "只标记，不删数据", "加上 is_outlier 等三列，原数据不动"),
    ("winsorize", "把极端值截断到正常范围", "样本量宝贵、不能删时用"),
    ("nan", "置为缺失值", "交给后续统计方法自行处理"),
]


class App:
    def __init__(self, root: tk.Tk, demo: bool = False) -> None:
        self.root = root
        self.demo = demo
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.input_path = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.group_col = tk.StringVar(value="（不分组）")
        self.vote_ratio = tk.StringVar(value="0.5")
        self.strategy = tk.StringVar(value="remove")
        self.columns: list[str] = []
        self.running = False
        self.last_outdir: Path | None = None

        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.root.title(APP_TITLE)
        # 按屏幕实际大小定窗口尺寸：小屏笔记本上不能让窗口超出屏幕
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(760, max(520, sw - 60))
        h = min(600, max(440, sh - 150))
        # 往下让一点：屏幕右上角常有输入法/上传悬浮条
        self.root.geometry(f"{w}x{h}+20+70")
        self.root.minsize(520, 440)

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=FONT_TITLE)
        style.configure("Sub.TLabel", font=FONT_SUB, foreground="#555555")
        style.configure("Go.TButton", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Opt.TRadiobutton", font=FONT)

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text=APP_SUB, style="Sub.TLabel").pack(anchor="w", pady=(0, 8))

        # --- 文件选择 ---
        box1 = ttk.LabelFrame(outer, text=" 1. 选择数据文件 ", padding=8)
        box1.pack(fill="x")
        row = ttk.Frame(box1)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.input_path, font=FONT).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览…", command=self._choose_file).pack(side="left", padx=(8, 0))
        row_hint = ttk.Frame(box1)
        row_hint.pack(fill="x", pady=(6, 0))
        ttk.Label(row_hint, text="支持 csv / Excel，第一行必须是列名。没数据可先试示例：",
                  style="Sub.TLabel").pack(side="left")
        ttk.Button(row_hint, text="载入示例数据并运行", command=self._use_sample).pack(side="left", padx=(6, 0))

        # --- 选项 ---
        box2 = ttk.LabelFrame(outer, text=" 2. 检测选项（不知道怎么选就用默认） ", padding=8)
        box2.pack(fill="x", pady=(8, 0))

        grid = ttk.Frame(box2)
        grid.pack(fill="x")

        ttk.Label(grid, text="分组列：", font=FONT).grid(row=0, column=0, sticky="w", pady=4)
        self.group_box = ttk.Combobox(grid, textvariable=self.group_col, state="readonly",
                                      width=26, font=FONT)
        self.group_box.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(grid, text="不同处理组/物种/批次的量纲不同，选它可以让每组独立判定",
                  style="Sub.TLabel").grid(row=0, column=2, sticky="w", padx=(10, 0))

        ttk.Label(grid, text="投票阈值：", font=FONT).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(grid, textvariable=self.vote_ratio, state="readonly", width=8, font=FONT,
                     values=["0.3", "0.4", "0.5", "0.6", "0.7"]).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(grid, text="被多少比例的检测器标记才算异常。0.5 = 多数票（推荐）",
                  style="Sub.TLabel").grid(row=1, column=2, sticky="w", padx=(10, 0))

        ttk.Label(box2, text="处理方式：", font=FONT).pack(anchor="w", pady=(6, 2))
        for value, label, note in STRATEGIES:
            line = ttk.Frame(box2)
            line.pack(anchor="w", fill="x")
            ttk.Radiobutton(line, text=label, value=value, variable=self.strategy,
                            style="Opt.TRadiobutton").pack(side="left")
            ttk.Label(line, text="— " + note, style="Sub.TLabel").pack(side="left", padx=(8, 0))

        # --- 输出 ---
        box3 = ttk.LabelFrame(outer, text=" 3. 输出目录 ", padding=8)
        box3.pack(fill="x", pady=(8, 0))
        row3 = ttk.Frame(box3)
        row3.pack(fill="x")
        ttk.Entry(row3, textvariable=self.out_dir, font=FONT).pack(side="left", fill="x", expand=True)
        ttk.Button(row3, text="选择…", command=self._choose_outdir).pack(side="left", padx=(8, 0))

        # --- 运行 ---
        self.run_btn = ttk.Button(outer, text="开始检测并生成报告", style="Go.TButton",
                                  command=self._start)
        self.run_btn.pack(fill="x", pady=(10, 6), ipady=5)

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x")

        # 先把底部一行占好位置，日志区最后打包——空间不够时压缩的是日志，不是按钮
        bottom = ttk.Frame(outer)
        bottom.pack(side="bottom", fill="x", pady=(6, 0))
        self.open_btn = ttk.Button(bottom, text="打开输出文件夹", state="disabled",
                                   command=self._open_outdir)
        self.open_btn.pack(side="left")
        ttk.Label(bottom, text="robustclean · MIT 开源内核", style="Sub.TLabel").pack(side="right")

        ttk.Label(outer, text="运行日志：", style="Sub.TLabel").pack(anchor="w", pady=(6, 2))
        log_frame = ttk.Frame(outer)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=6, font=("Consolas", 9), wrap="word",
                           background="#f7f8fa", relief="flat")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

        if self.demo:
            self.root.after(500, self._use_sample)

    # ------------------------------------------------------------------
    @staticmethod
    def sample_csv() -> Path | None:
        """示例数据的位置（开发时在仓库里，打包后在 exe 内部）。"""
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        for cand in (base / "sample" / "penguins_size.csv",
                     base / "examples" / "data" / "penguins_size.csv"):
            if cand.exists():
                return cand
        return None

    def _use_sample(self) -> None:
        path = self.sample_csv()
        if path is None:
            messagebox.showwarning(APP_TITLE, "没有找到示例数据文件")
            return
        self.input_path.set(str(path))
        self.out_dir.set(str(Path.home() / "Desktop" / "清洗结果_示例"))
        self._load_columns(path)
        if self.columns:
            # 企鹅数据按物种分组才有意义，示例自动选上
            for guess in ("species", "组别", "group", "分组"):
                if guess in self.columns:
                    self.group_col.set(guess)
                    break
        self._log("已载入示例数据（企鹅形态数据，344 行），正在开始运行…")
        self.root.after(300, self._start)

    # ------------------------------------------------------------------
    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择数据文件",
            filetypes=[("数据文件", "*.csv *.xlsx *.xls"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.input_path.set(path)
        p = Path(path)
        if not self.out_dir.get():
            self.out_dir.set(str(p.parent / "清洗结果"))
        self._load_columns(p)

    def _choose_outdir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_dir.set(path)

    def _load_columns(self, path: Path) -> None:
        """读表头，把列名填进分组下拉框。"""
        try:
            import pandas as pd

            if path.suffix.lower() in {".xlsx", ".xls"}:
                df = pd.read_excel(path, nrows=5)
            else:
                df = None
                for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
                    try:
                        df = pd.read_csv(path, nrows=5, encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if df is None:
                    df = pd.read_csv(path, nrows=5, encoding="utf-8", errors="replace")
            self.columns = [str(c) for c in df.columns]
            self.group_box.configure(values=["（不分组）"] + self.columns)
            self.group_col.set("（不分组）")
            self._log(f"已读取：{path.name}")
            self._log(f"  共 {len(self.columns)} 列：{'、'.join(self.columns[:8])}"
                      + ("…" if len(self.columns) > 8 else ""))
        except Exception as exc:  # noqa: BLE001
            self._log(f"读取表头失败：{exc}")
            messagebox.showerror(APP_TITLE, f"读取文件失败：\n{exc}")

    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self) -> None:
        if self.running:
            return
        src = self.input_path.get().strip()
        if not src:
            messagebox.showwarning(APP_TITLE, "请先选择数据文件")
            return
        if not Path(src).exists():
            messagebox.showerror(APP_TITLE, "文件不存在")
            return
        out = self.out_dir.get().strip() or str(Path(src).parent / "清洗结果")
        self.out_dir.set(out)

        self.running = True
        self.run_btn.configure(state="disabled", text="正在检测，请稍候…")
        self.open_btn.configure(state="disabled")
        self.progress.start(12)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        args = dict(
            src=src,
            out=out,
            group=None if self.group_col.get() == "（不分组）" else self.group_col.get(),
            vote=float(self.vote_ratio.get()),
            strategy=self.strategy.get(),
        )
        threading.Thread(target=self._worker, kwargs=args, daemon=True).start()
        self.root.after(100, self._poll)

    def _worker(self, src: str, out: str, group: str | None, vote: float, strategy: str) -> None:
        try:
            import pandas as pd

            from .pipeline import RobustCleaner

            path = Path(src)
            if path.suffix.lower() in {".xlsx", ".xls"}:
                df = pd.read_excel(path)
            else:
                df = None
                for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
                    try:
                        df = pd.read_csv(path, encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if df is None:
                    df = pd.read_csv(path, encoding="utf-8", errors="replace")

            self.queue.put(("log", f"数据读入完成：{len(df)} 行 × {df.shape[1]} 列"))
            numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
                       and c != group]
            self.queue.put(("log", f"参与检测的数值列（{len(numeric)} 个）：{'、'.join(map(str, numeric))}"))
            if group:
                self.queue.put(("log", f"按「{group}」分组，组内独立判定"))
            self.queue.put(("log", ""))
            self.queue.put(("log", "正在运行 9 个检测器，这一步通常几秒到几十秒…"))

            cleaner = RobustCleaner(vote_ratio=vote, group_column=group)
            cleaner.fit(df, columns=numeric)

            for row in cleaner.summary().itertuples(index=False):
                self.queue.put(("log", f"  {row[0]:<28} 标记 {row[2]:>4} 个  ({row[3]}%)"))

            cons = cleaner.consensus_
            self.queue.put(("log", ""))
            self.queue.put(("log", f"共识判定异常：{cons.n_flagged} 个（{100 * cons.flag_ratio:.2f}%）"))

            if cleaner.skipped_:
                for k, v in cleaner.skipped_.items():
                    self.queue.put(("log", f"  跳过 {k}：{v}"))

            self.queue.put(("log", ""))
            self.queue.put(("log", "正在生成报告、图表和论文段落…"))
            result = cleaner.save(out, df, strategy=strategy)
            self.queue.put(("done", result))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("error", f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    self._finish(payload)
                    return
                elif kind == "error":
                    self._fail(str(payload))
                    return
        except queue.Empty:
            pass
        if self.running:
            self.root.after(120, self._poll)

    def _finish(self, result: dict) -> None:
        self.running = False
        self.progress.stop()
        self.run_btn.configure(state="normal", text="开始检测并生成报告")
        outdir = Path(result["cleaned"]).parent
        self.last_outdir = outdir
        self.open_btn.configure(state="normal")

        self._log("")
        self._log("完成。生成的文件：")
        for key, label in (("cleaned", "清洗后的数据"), ("outliers", "被剔除的样本"),
                           ("report", "完整报告"), ("methods", "论文方法学段落"),
                           ("sensitivity", "敏感性分析表"), ("audit", "审计日志")):
            self._log(f"  · {label}：{Path(result[key]).name}")
        for fig in result.get("figures", []):
            self._log(f"  · 图表：{Path(fig).name}")
        self._log(f"\n全部文件在：{outdir}")

        if not self.demo:
            messagebox.showinfo(
                APP_TITLE,
                f"处理完成！\n\n"
                f"报告：{Path(result['report']).name}\n"
                f"论文段落：{Path(result['methods']).name}\n\n"
                f"输出目录：\n{outdir}",
            )

    def _fail(self, msg: str) -> None:
        self.running = False
        self.progress.stop()
        self.run_btn.configure(state="normal", text="开始检测并生成报告")
        self._log("出错了：")
        self._log(msg)
        head = msg.splitlines()[0] if msg else "未知错误"
        messagebox.showerror(APP_TITLE, f"处理失败：\n\n{head}")

    def _open_outdir(self) -> None:
        if not self.last_outdir or not self.last_outdir.exists():
            return
        try:
            import os
            os.startfile(str(self.last_outdir))  # noqa: S606
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"打开失败：{exc}")


def main(demo: bool = False) -> int:
    if "--demo" in sys.argv:
        demo = True
    root = tk.Tk()
    App(root, demo=demo)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
