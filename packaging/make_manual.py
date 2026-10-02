"""生成中文图文操作手册（单个 HTML 文件，图片内嵌，双击即可打开）。"""

from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "packaging" / "shots"


def img_tag(path: Path, caption: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<figure><img src="data:image/png;base64,{data}" alt="{caption}">'
        f"<figcaption>{caption}</figcaption></figure>"
    )


HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>科研数据清洗工具箱 · 操作手册</title>
<style>
  :root { --navy:#12233c; --teal:#37beac; --coral:#e85d3e; --muted:#6b7c90; }
  * { box-sizing: border-box; }
  body {
    margin: 0 auto; max-width: 860px; padding: 48px 32px 96px;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    color: #1b2733; line-height: 1.85; font-size: 16px;
  }
  h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: .5px; }
  .sub { color: var(--muted); margin: 0 0 36px; font-size: 15px; }
  h2 {
    font-size: 21px; margin: 44px 0 12px; padding-left: 12px;
    border-left: 4px solid var(--teal);
  }
  h3 { font-size: 17px; margin: 26px 0 8px; }
  p, li { font-size: 16px; }
  code {
    background: #f2f4f7; padding: 1px 6px; border-radius: 4px;
    font-family: Consolas, monospace; font-size: 14px;
  }
  .tip {
    background: #f0f9f7; border-left: 4px solid var(--teal);
    padding: 12px 16px; margin: 16px 0; border-radius: 0 6px 6px 0;
  }
  .warn {
    background: #fdf3f0; border-left: 4px solid var(--coral);
    padding: 12px 16px; margin: 16px 0; border-radius: 0 6px 6px 0;
  }
  figure { margin: 20px 0; text-align: center; }
  figure img {
    max-width: 100%; border: 1px solid #dfe4ea; border-radius: 8px;
    box-shadow: 0 4px 16px rgba(20,40,70,.10);
  }
  figcaption { color: var(--muted); font-size: 14px; margin-top: 8px; }
  table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 15px; }
  th, td { border-bottom: 1px solid #e3e8ee; padding: 9px 10px; text-align: left; vertical-align: top; }
  th { background: #f6f8fa; font-weight: 600; }
  .step { counter-increment: step; }
  ol.steps { padding-left: 22px; }
  ol.steps > li { margin: 10px 0; }
  .qa { margin: 18px 0; }
  .qa b { display: block; margin-bottom: 4px; }
  footer { margin-top: 60px; padding-top: 16px; border-top: 1px solid #e3e8ee;
           color: var(--muted); font-size: 14px; }
  @media print {
    body { padding: 0 16px; max-width: none; }
    figure img { box-shadow: none; }
    h2 { page-break-after: avoid; }
    figure { page-break-inside: avoid; }
  }
</style>
</head>
<body>
"""


def build() -> str:
    shot_main = img_tag(SHOTS / "main.png", "图 1　主界面：三个步骤，一目了然")
    shot_result = img_tag(SHOTS / "result.png", "图 2　点击「载入示例数据并运行」后自动填好并开始")

    return HTML_HEAD + f"""
<h1>科研数据清洗工具箱 · 操作手册</h1>
<p class="sub">九个检测器投票判定异常值 · 一键生成可用于论文的清洗报告</p>

<div class="tip">
<b>三句话上手：</b>双击程序 → 选你的数据文件 → 点「开始检测并生成报告」。
不知道选什么就全部用默认值，默认值适用于大多数情况。
</div>

<h2>一、启动程序</h2>
<ol class="steps">
  <li>把收到的压缩包解压到任意位置（比如桌面）。<b>必须先解压</b>，不要直接在压缩包里双击运行。</li>
  <li>打开解压出来的文件夹，双击 <code>科研数据清洗工具箱.exe</code>。</li>
  <li>第一次启动可能需要等 3–8 秒（程序在加载计算库），这是正常的。</li>
</ol>
<div class="warn">
如果 Windows 弹出蓝色的「Windows 已保护你的电脑」提示，点<b>「更多信息」→「仍要运行」</b>。
这是因为程序没有购买数字签名证书（个人开发者常见），不是病毒。程序全程在你电脑本地运行，不联网、不上传任何数据。
</div>

{shot_main}

<h2>二、选择数据文件</h2>
<p>点「浏览…」，选择你的数据文件。支持两种格式：</p>
<table>
  <tr><th>格式</th><th>说明</th></tr>
  <tr><td><code>.csv</code></td><td>逗号分隔的文本表，Excel 另存为即可</td></tr>
  <tr><td><code>.xlsx</code></td><td>Excel 工作簿，只读取第一个工作表</td></tr>
</table>
<p><b>要求：第一行必须是列名</b>（比如「处理组、株高、叶面积」），从第二行开始才是数据。</p>

<h3>没有数据？先点「载入示例数据并运行」</h3>
<p>程序自带一份 344 行的企鹅形态数据，点这个按钮会自动填好、自动运行，
让你先看一遍完整流程长什么样。跑完的结果在桌面的「清洗结果_示例」文件夹里。</p>

{shot_result}

<h2>三、选检测选项（不知道怎么选就用默认）</h2>

<h3>分组列</h3>
<p>如果你的数据里有「处理组」「物种」「批次」「地点」这类分类型的列，
<b>强烈建议选它</b>。</p>
<p>原因：不同组的量纲和分布本来就不一样。比如对照组平均株高 20 cm、处理组 45 cm，
如果把两组混在一起检测，整个处理组都会被判成「异常」。选了分组列之后，
比较只在组内进行，就不会出现这种误判。</p>

<h3>投票阈值</h3>
<p>程序用了 9 个原理不同的检测器，每个各投一票。「投票阈值」就是——
<b>被多少比例的检测器标记，才算异常</b>。</p>
<table>
  <tr><th>取值</th><th>效果</th><th>什么时候用</th></tr>
  <tr><td>0.5（默认）</td><td>多数票，被 5 个以上标记才算</td><td>绝大多数情况</td></tr>
  <tr><td>0.7</td><td>更严格，只剔除证据非常充分的</td><td>数据珍贵、不想误删</td></tr>
  <tr><td>0.3</td><td>更激进，剔除得更彻底</td><td>怀疑数据质量差、想先看看有多少问题</td></tr>
</table>

<h3>处理方式</h3>
<table>
  <tr><th>选项</th><th>做了什么</th><th>什么时候选</th></tr>
  <tr><td><b>直接删除异常样本</b></td><td>把判定的样本从表里删掉</td><td>确认是测量错误（默认）</td></tr>
  <tr><td>只标记，不删数据</td><td>原始数据一行不少，额外加三列标记</td><td>要给审稿人看原始数据，或想先人工复核</td></tr>
  <tr><td>把极端值截断到正常范围</td><td>保留样本，只把数值压回正常区间</td><td>样本量宝贵、不能删</td></tr>
  <tr><td>置为缺失值</td><td>被判定的数值变成空值</td><td>后续统计方法本身能处理缺失</td></tr>
</table>
<div class="tip">
<b>拿不准就用「只标记，不删数据」跑第一遍。</b>看看被判定的都是哪些样本，
符合你的领域判断再改成「直接删除」跑第二遍。这也比直接删更安全——跑了就撤不回来了。
</div>

<h2>四、输出目录</h2>
<p>默认会在数据文件旁边建一个「清洗结果」文件夹。可以自己选别的位置，比如桌面。</p>

<h2>五、点「开始检测并生成报告」</h2>
<p>344 行的数据大约 10 秒；几千行大约 30 秒到 1 分钟。运行期间窗口不会卡住，
底部的日志会实时显示每个检测器的判定结果。</p>

<h2>六、结果里有什么（10 个文件）</h2>
<table>
  <tr><th>文件</th><th>是什么</th><th>怎么用</th></tr>
  <tr><td><code>cleaned.csv</code></td><td>清洗后的数据</td><td>直接拿去做后续分析</td></tr>
  <tr><td><code>outliers.csv</code></td><td>被剔除的样本（含原始数据）</td><td>逐条核对「到底删了谁」，也可以写进附录</td></tr>
  <tr><td><code>outlier_detail_all.csv</code></td><td>每个样本的判定明细</td><td>看某个样本被哪几个检测器标记了</td></tr>
  <tr><td><code>report.md</code></td><td>完整报告</td><td>方法的完整说明 + 投票分布 + 敏感性分析</td></tr>
  <tr><td><b><code>methods_paragraph.md</code></b></td><td><b>论文方法学段落</b></td><td><b>中英文各一段，改掉占位内容就能直接粘进论文</b></td></tr>
  <tr><td><code>sensitivity.csv</code></td><td>剔除前后统计量表</td><td>回答审稿人「删数据会不会影响结论」</td></tr>
  <tr><td><code>detector_summary.csv</code></td><td>各检测器标记数量</td><td>方法学表格的素材</td></tr>
  <tr><td><code>audit.json</code></td><td>审计日志</td><td>记录全部参数、随机种子、软件版本，用于复现</td></tr>
  <tr><td><code>fig1_*.png</code></td><td>共识分数分布图</td><td>可直接放进论文补充材料</td></tr>
  <tr><td><code>fig2_*.png</code></td><td>PCA 投影图（标出异常点）</td><td>同上</td></tr>
</table>

<h2>七、怎么把它写进论文</h2>
<ol class="steps">
  <li>打开 <code>methods_paragraph.md</code>，里面有中文和英文两段现成的方法学描述。</li>
  <li>把里面的软件版本号、变量名替换成你自己的。</li>
  <li>数字（剔除数量、占比）程序已经自动填好了，直接抄。</li>
  <li>在论文里加一句：完整参数与逐样本判定明细见附件（把 <code>audit.json</code> 作为补充材料上传）。</li>
  <li>如果审稿人质疑，用 <code>sensitivity.csv</code> 回答——它直接展示了剔除前后均值、标准差、偏度的变化。</li>
</ol>
<div class="tip">
<b>最有说服力的一句话</b>：如果敏感性分析显示剔除前后均值变化小于 1%，
你可以在论文里写「结果表明异常值处理未实质影响主要结论」——这是审稿人最想看到的。
</div>

<h2>八、常见问题</h2>

<div class="qa"><b>Q：我的数据是 Excel，需要先转成 CSV 吗？</b>
不需要，直接选 <code>.xlsx</code> 就行。程序读第一个工作表。</div>

<div class="qa"><b>Q：提示「没有找到可用的数值列」？</b>
说明你的数据列被识别成了文本。常见原因是数字里混了单位（比如「12.5 cm」）或者
有中文的「缺失」「无」这类占位词。把它们清理成纯数字就可以了。</div>

<div class="qa"><b>Q：提示某个分组「有效样本数 &lt; 10，跳过」？</b>
组内样本少于 10 个时，任何异常值检测都没有统计意义，程序会自动跳过该组，
并在这组样本的判定里写「保留」。这是刻意的保护，不是 bug。</div>

<div class="qa"><b>Q：数据里有空的单元格怎么办？</b>
程序会用<b>组内中位数</b>临时填补，<b>只在检测阶段使用</b>，你原始数据不会被改动。
报告第一节会写明填补了几个值。如果某一整行全是空的，这一行不参与检测——
它属于缺失数据，不是异常值。</div>

<div class="qa"><b>Q：剔除得太多了 / 太少了？</b>
太多了：把投票阈值调到 0.7。<br>
太少了：调到 0.3，或者检查是不是忘了选分组列。</div>

<div class="qa"><b>Q：能撤销吗？</b>
能。程序<b>从不修改你的原始文件</b>，只在输出目录生成新文件。
删掉输出文件夹就等于撤销。这也是建议先用「只标记，不删数据」的原因。</div>

<div class="qa"><b>Q：我的数据会被上传吗？</b>
不会。程序全程在你电脑本地运行，不联网。你可以断网测试。</div>

<div class="qa"><b>Q：支持多少个变量、多少行？</b>
几十个变量、几万行都没问题。变量特别多（超过 50 个）时，建议先用「只标记」跑一遍，
看看结果是否合理——高维数据里距离类方法会变迟钝。</div>

<h2>九、这套方法凭什么可信</h2>
<ul>
  <li><b>不依赖单一方法。</b>九个检测器的原理互不相同（稳健 Z 分数、箱线图准则、马氏距离、
  PCA 重构误差、k 近邻距离、局部离群因子、孤立森林、密度聚类、高斯混合模型），
  各自的盲区不重叠，投票能互相补位。</li>
  <li><b>判据不会被异常值污染。</b>全部使用中位数、MAD、分位数这类稳健统计量，
  不用均值和标准差（它们本身就会被极端值带偏）。</li>
  <li><b>有基准测试。</b>在四类异常值、每类 800 样本的合成数据上，共识方法的平均 F1
  为 0.883，优于均值±3σ（0.753）、IQR（0.705）、孤立森林（0.699）、LOF（0.619）。
  在单变量看不出来的多变量组合异常场景下差距最大：0.779 对 0.321。</li>
  <li><b>过程可复现。</b>全部参数、随机种子、软件版本都记在 <code>audit.json</code> 里。</li>
</ul>

<footer>
科研数据清洗工具箱 · 内核基于开源项目 robustclean（MIT 协议）<br>
遇到本手册没覆盖的问题，欢迎直接联系我。
</footer>
</body>
</html>
"""


def main() -> int:
    html = build()
    out = ROOT / "packaging" / "使用手册.html"
    out.write_text(html, encoding="utf-8")
    print(f"OK {out}  {out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
