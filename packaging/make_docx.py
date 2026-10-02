"""生成 Word 版论文方法学模板（中英对照）。"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging" / "论文方法学模板.docx"

ZH = (
    "本研究采用多检测器共识策略识别数据中的异常值"
    "【若分组：，并在变量「{分组列名}」的每个水平内分别执行】。"
    "参与判定的检测器包括 MAD 稳健 Z 分数、IQR 箱线图准则、马氏距离（以最小协方差行列式稳健估计协方差）、"
    "主成分重构误差、k 近邻距离、局部离群因子（LOF）、孤立森林、密度聚类噪声点与高斯混合模型，共 9 种。"
    "各检测器先输出连续的异常分数，再经稳健秩变换归一化后等权融合；"
    "当某样本被不低于 {投票阈值} 的检测器判为异常时，判定为异常值。"
    "据此共识别出 {异常样本数} 个异常样本，占全部 {样本总数} 个样本的 {异常占比}，"
    "这些样本未纳入后续统计分析。敏感性分析显示，剔除前后各变量的均值变化幅度为 "
    "{均值最大变化幅度}，表明异常值处理未实质影响本研究的主要结论。"
    "全部检测器及其参数、阈值与逐样本判定明细见补充材料。"
)

EN = (
    "Outliers were identified using a multi-detector consensus procedure"
    "{applied within each level of [GROUP VARIABLE]}. "
    "The following detectors were applied: robust MAD-based Z score, Tukey IQR criterion, "
    "Mahalanobis distance with minimum covariance determinant estimation, Principal Component "
    "Analysis reconstruction error, k-nearest-neighbour distance, Local Outlier Factor, Isolation "
    "Forest, DBSCAN noise detection, and a Gaussian Mixture Model. "
    "Each detector produced a continuous outlier score; scores were converted to robust ranks and "
    "combined with equal weights. A sample was labelled as an outlier when at least [THRESHOLD] of "
    "the detectors flagged it. This procedure identified [N OUTLIERS] of [N TOTAL] observations "
    "([PERCENT]), which were excluded from downstream analyses. Sensitivity analysis showed that "
    "the change in variable means after exclusion was [MAX CHANGE], indicating that outlier "
    "handling did not materially affect the main conclusions of this study. "
    "All detector parameters, thresholds and per-sample decisions are provided in the Supplementary "
    "Material."
)


def set_zh_font(doc: Document, name: str = "Microsoft YaHei") -> None:
    style = doc.styles["Normal"]
    style.font.name = name
    style.font.size = Pt(11)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)


def add_note(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x6B, 0x7C, 0x90)


def main() -> int:
    doc = Document()
    set_zh_font(doc)

    h = doc.add_heading("论文方法学段落模板（异常值处理）", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT

    add_note(
        doc,
        "用法：把下面两段里的【方括号】内容替换成你自己的实际数字，其余可直接使用。"
        "所有数字都能在程序输出的 methods_paragraph.md 和 sensitivity.csv 里找到，无需自己计算。",
    )

    doc.add_heading("一、中文（替换方括号内容后可直接使用）", level=1)
    p = doc.add_paragraph(ZH)
    p.paragraph_format.line_spacing = 1.5

    doc.add_heading("二、English（replace the bracketed parts）", level=1)
    p = doc.add_paragraph(EN)
    p.paragraph_format.line_spacing = 1.5

    doc.add_heading("三、各占位内容从哪里取", level=1)
    rows = [
        ("占位内容", "从哪里取"),
        ("分组列名", "程序界面上你选的那个列名（没分组就删掉这句）"),
        ("投票阈值", "程序界面上的「投票阈值」，默认 0.5（写成 50%）"),
        ("样本总数", "report.md 第 1 节「样本数」"),
        ("异常样本数 / 异常占比", "report.md 第 3 节「共识结果」"),
        ("均值最大变化幅度", "sensitivity.csv 里「均值变化%」一列取绝对值最大者"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for i, (a, b) in enumerate(rows):
        cells = table.add_row().cells
        cells[0].text = a
        cells[1].text = b
        if i == 0:
            for c in cells:
                for para in c.paragraphs:
                    for run in para.runs:
                        run.bold = True

    doc.add_heading("四、敏感性分析表（可直接放进补充材料）", level=1)
    add_note(doc, "把 sensitivity.csv 的内容粘进下表即可，或在报告里说明表格见附件。")
    t2 = doc.add_table(rows=1, cols=6)
    t2.style = "Table Grid"
    headers = ["变量", "剔除点数", "均值（剔除前）", "均值（剔除后）", "标准差（前→后）", "偏度（前→后）"]
    for i, htext in enumerate(headers):
        cell = t2.rows[0].cells[i]
        cell.text = htext
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    for _ in range(4):
        t2.add_row()

    doc.add_heading("五、投稿前自查清单", level=1)
    for item in [
        "方法学段落里的数字与 report.md 一致（样本数、剔除数、占比）。",
        "说明了为什么用多方法而不是单一方法（一句话即可：单一方法存在系统性盲区）。",
        "报告了剔除比例，而不是只写「已剔除异常值」。",
        "给出了敏感性分析结果，说明结论不依赖于删数据。",
        "补充材料里包含 audit.json，说明分析可复现。",
        "如果审稿人要求，能提供被剔除样本的原始数据（outliers.csv 里已经有）。",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("六、被问到时的回答参考", level=1)
    qa = [
        ("为什么不用均值±3σ？",
         "均值和标准差由全部样本计算，会被异常值本身撑大，导致极端值反而检测不出来。"
         "本研究使用的判据全部基于中位数与 MAD 等稳健统计量。"),
        ("为什么剔除这些样本？",
         "判定并非来自单一方法，而是九个原理互不相同的检测器投票的结果；"
         "被判定样本的逐条判定依据见补充材料中的逐样本明细表。"),
        ("剔除后结论会变吗？",
         "敏感性分析显示关键变量均值的变化幅度为【填数字】，主要结论未发生实质变化。"),
    ]
    for q, a in qa:
        p = doc.add_paragraph()
        r = p.add_run("问：" + q)
        r.bold = True
        doc.add_paragraph("答：" + a)

    doc.save(OUT)
    print(f"OK {OUT}  {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
