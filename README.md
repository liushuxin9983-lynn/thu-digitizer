<p align="center">
  <img src="assets/thu-digitizer-hero-handdrawn-white.png" alt="THU Digitizer" width="920">
</p>

<p align="center">
  <img alt="Input" src="https://img.shields.io/badge/Input-chart_images_%2B_PDF-6F42A1?style=for-the-badge">
  <img alt="Output" src="https://img.shields.io/badge/Output-CSV_%2B_JSON_%2B_overlay-25A9E0?style=for-the-badge">
  <img alt="Workflow" src="https://img.shields.io/badge/Workflow-local_%2B_auditable-39A96B?style=for-the-badge">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-FF6699?style=for-the-badge">
</p>

# THU Digitizer

THU Digitizer 是一个研究优先的科研图表数字化 skill：从图片和 PDF 图中恢复**肉眼可见、坐标可校准、结果可复核**的数值，并把 CSV、JSON 报告、覆盖图、校准参数和来源记录一起保存下来。

它的核心特点是：

- 先分类再提取：先识别输入类型、图表语法、坐标体系和目标面板，再选择专用路线；未知或不兼容图表不会被强行塞进通用 XY 提取器。
- 本地确定性执行：已注册的脚本负责真正的数值输出，模型只辅助提出图表类型、绘图区、标定点和颜色等候选信息。
- 证据随结果交付：除 CSV 外，同时保留输入哈希、FigureSpec、参数、置信度、诊断、JSON 报告和 overlay/recreation，方便逐点检查。
- 保守拒绝：看不清、被遮挡、无法唯一匹配或校准不充分时，返回 `low_confidence`、`not_extracted` 或拒绝数值输出，而不是补出一个看似完整的表格。
- 源数据独立验证：论文附带的 XLSX/CSV 用于单独验证可见提取结果，不会反向改写原始 digitization CSV。

它的目标不是“一键猜出所有数据”，而是把科研图表数字化变成一条可重复、可审计、知道边界的证据链。

## 适合什么

- 从折线图、直方图和填充箱线图中恢复可见数值。
- 对散点、分组/堆叠柱图、热图、轮廓箱线图等候选路线进行受约束提取与覆盖图复核。
- 优先检查 PDF 中的矢量路径、标记和文字，再决定直接恢复几何信息还是转入栅格流程。
- 用论文官方补充表、CSV 或工作簿验证图中可见点、区间或汇总值。
- 为论文复核、系统综述、复现研究和图表重绘准备带来源与置信度的数据。
- 通过本地 OA Figure Gallery 查看原图、提取覆盖、CSV、复现图和能力边界。

## 输出内容

一次完整任务通常会生成两层结果：面向使用的数据文件，以及面向复核的证据包。数据文件只包含获得授权的可见提取值；证据包解释这些值从哪里来、如何校准、哪些内容没有被提取。

<details>
<summary>展开完整输出清单</summary>

常见数据文件：

- `data.csv` 或任务指定的提取 CSV
- 单独保存的 `source-validation.csv`
- 从提取值绘制的 `recreated.png`

常见证据文件：

- `preflight-report.json`：输入、候选图表类型与保守路由结果
- `figure-spec.json`：面板、绘图区、坐标轴、变换、系列和校准确认项
- `report.json`：输入哈希、算法版本、参数、置信度、诊断与拒绝原因
- `overlay.png`：把接受或拒绝的图元叠加回原图检查
- `vector-inspection.json`：PDF 页面中的路径、标记、颜色和几何统计
- 源数据验证 JSON、identity plot 或对比 overlay

</details>

## 当前能力边界

| 成熟度 | 当前路线 | 使用要求 |
| --- | --- | --- |
| 稳定 | 颜色可分离的校准折线、直方图、纵向/横向填充箱线图 | 明确面板、绘图区、坐标标定与颜色；通过本地回归门槛 |
| 候选 | 紧凑填充散点、简单/分组/堆叠柱图、连续轨迹模式、热图、轮廓箱线图、矢量 PDF 剂量反应图 | 必须检查 overlay、诊断、覆盖率和每类路线的额外确认项 |
| 辅助 | 通用 PDF 矢量检查、官方源数据验证 | 需要人工确认图元语义、坐标变换与面板映射 |
| 拒绝 | 未知图表、未实现的非笛卡尔坐标、无法唯一识别或校准的图元 | 只输出路由诊断，不授权数值结果 |

能力索引中的图表类型不等于已经稳定支持。路线成熟度以 [`scripts/extractor_registry.py`](scripts/extractor_registry.py)、[`SKILL.md`](SKILL.md) 和对应基准证据为准。

## 快速使用

### 1. 安装

把下面这句话发给 Agent：

```text
请帮我安装这个 skill：
https://github.com/Rimagination/thu-digitizer
```

### 2. 提取图表

把图表图片或论文 PDF 发给 Agent，然后说：

```text
请用 THU Digitizer 检查这张图，确认图表类型和坐标后提取可见数据，
并保留 CSV、JSON 报告、overlay、来源记录和拒绝状态。
```

如果是 PDF，请同时说明页码和目标面板；如果没有说明，Agent 会先做预检，不会直接猜值。

### 3. 验证与保存

如果论文提供官方源数据，可以继续说：

```text
请把提取结果与这份官方工作簿做独立验证，不要覆盖原始提取 CSV，
并把结果保存到：“D:\科研数据\figure-digitization” 里。
```

## 命令行预检

核心 CLI 先列出路由、检查输入并生成待确认的 FigureSpec；它不会把“找到候选路线”等同于“已经可以提取”。

```powershell
python scripts\thu_digitizer.py routes

python scripts\thu_digitizer.py inspect `
  --input figure.png `
  --chart-type histogram `
  --output-report preflight-report.json `
  --output-spec figure-spec.json

python scripts\thu_digitizer.py validate-spec `
  --spec figure-spec.json
```

如果图表类型未知，可以省略 `--chart-type`。预检会返回 `needs_chart_type_confirmation`，等待确认后再进入对应提取器。

## 依赖与环境

核心预检和基础提取使用 Python 3.10+，主要依赖 NumPy、Pillow 和 PyMuPDF：

```powershell
python -m pip install numpy pillow pymupdf
```

基准、画廊构建和部分验证脚本还会按需使用 Matplotlib、SciPy、OpenPyXL 和 OpenCV。普通使用不需要先安装所有开发依赖。

| 层级 | 用来做什么 | 主要依赖 |
| --- | --- | --- |
| 核心 | 路由预检、栅格标定、基础提取、PDF 矢量检查 | Python、NumPy、Pillow、PyMuPDF |
| 候选路线 | 散点分割与更复杂的图像几何 | OpenCV、对应路线脚本 |
| 验证与画廊 | 重绘、统计比较、工作簿读取和证据构建 | Matplotlib、SciPy、OpenPyXL |
| 开发测试 | 运行完整回归套件 | `unittest` 与上述相关依赖 |

默认工作流在本地运行。只有用户明确批准时，才可以把图像交给远程 OCR 或视觉模型服务。

## 本地画廊

仓库自带一个静态 OA Figure Gallery，用来并排查看原图、覆盖图、数据复现、CSV 和能力成熟度：

```powershell
python -m http.server 8793 --bind 127.0.0.1 --directory gallery
```

然后打开 <http://127.0.0.1:8793/>。画廊中的类型索引用于路由和研究规划；只有带明确提取证据与成熟度标记的案例才能作为能力证明。

## 图表数字化原则

- 先验证面板、坐标系、轴变换和图例，再接受任何数值。
- 优先使用 PDF/SVG 中可验证的矢量对象；矢量语义不清时回退到受校准的栅格流程。
- 只恢复图上可见的点、线、柱、箱体、误差端点或色块，不推断隐藏原始样本和作者拟合参数。
- 保留空缺和遮挡；不为了表格完整而插值或从官方工作簿回填。
- 图像提取与源数据验证分开保存，报告配对覆盖率、单位变换和不可比较项。
- 新路线只有在合成、真实矢量、真实栅格和跨工具比较门槛通过后，才能从候选提升为稳定。

## 相关文件

- [`SKILL.md`](SKILL.md)：Agent 使用 THU Digitizer 时读取的完整工作流和边界。
- [`scripts/thu_digitizer.py`](scripts/thu_digitizer.py)：统一路由、预检和 FigureSpec 入口。
- [`scripts/extractor_registry.py`](scripts/extractor_registry.py)：稳定、候选、辅助与拒绝路线的机器可读注册表。
- [`scripts/figure_spec.py`](scripts/figure_spec.py)：面板、坐标、系列、校准和确认状态契约。
- [`references/research-quality-baseline.md`](references/research-quality-baseline.md)：研究质量门槛和候选路线提升规则。
- [`references/official-source-data-validation.md`](references/official-source-data-validation.md)：官方源数据独立验证规范。
- [`gallery/`](gallery/)：OA 案例、能力地图、CSV、overlay 和交互复现。
- [`scripts/`](scripts/)：提取器、构建脚本、基准和回归测试。

## 开发测试

在 `scripts/` 目录发现并运行全部 `unittest`：

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

大型或一次性基准运行应放在仓库外的临时目录，只把可复现的小型 fixture、清单和必要证据纳入版本控制。

## 致谢

THU Digitizer 的研究基线和实现受这些工具与生态启发或支持：

- [WebPlotDigitizer](https://automeris.io/)：交互式坐标校准与图表数字化的重要比较基线。
- [PyMuPDF](https://pymupdf.readthedocs.io/)：PDF 页面与矢量对象检查。
- [NumPy](https://numpy.org/)、[Pillow](https://python-pillow.org/)、[Matplotlib](https://matplotlib.org/)、[SciPy](https://scipy.org/) 和 [OpenCV](https://opencv.org/)：本地几何处理、统计验证和证据可视化。
- 画廊中的开放获取论文与作者公开源数据；具体来源、许可和用途记录在各案例及 [`gallery/ATTRIBUTION.md`](gallery/ATTRIBUTION.md) 中。

## 许可证

本项目使用 [MIT License](LICENSE)。
