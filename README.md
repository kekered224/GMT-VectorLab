# GMT VectorLab

> 画布式 GMT 改图工具 —— 不改你的源脚本，直接在原图上拖拽、缩放、旋转、改文字，并高清导出。

GMT（Generic Mapping Tools）是科学制图的业界标准，但它的渲染是“命令 → 图像”的无状态流程：一旦出图，**没有可点选的对象场景图**，想微调一个标题、挪一下站点符号，只能回去改脚本、重跑。

现在多数脚本由 AI 生成。第一版通常能用，但离出版还差最后一点：字号、图例位置、配色、标注排布 —— 这些用对话交代不清，只能一轮轮改，而每改一处就要整图重画一次，时间和 token 都花在重画上。

GMT VectorLab 的分工很明确：**AI 出出版级底稿，你来定终版**。

GMT VectorLab 在这一点上补了一层可视化编辑：

- **命令级 overlay**：把源脚本解析成结构化图层，你的所有微调写进独立的 `overlay.json`，重渲染时叠加。**源脚本永远只读**（每次渲染前后比对 sha256 强校验）。
- **画布级编辑**：把 GMT 出的 PDF 重建为“每个元素独立可寻址、文字仍是真文字”的 SVG，在画布上**点选 / 拖拽 / 缩放 / 旋转 / 改文字**，支持多选、撤销重做。
- **高清导出**：一键导出 **PNG**（最高画质）或 **JPG**（自定义 DPI，默认 300，科研绘图建议 ≥300）。

整个工具是一个原生桌面窗口（pywebview + WebView2），不开浏览器、不占端口。

---

## 特性一览

- 打开任意 GMT 脚本（任意文件名、任意位置），其所在目录即工作目录。
- 两种编辑模式：
  - **命令模式**：勾选图层、改选项（如 `-R`、`-W`、`-G`），立即重渲染。
  - **画布模式**：在渲染出的图上直接拖拽元素；拖角等比缩放、拖边单轴拉伸（PPT 式手感）、拖顶部旋转；双击改文字。
- 源脚本只读守护：任何改动都不写回源脚本，只存为 overlay。
- 导出 PNG / JPG，JPG 按 DPI 设定分辨率。

---

## 环境要求

| 依赖 | 说明 |
| --- | --- |
| **GMT 6.x** | 在用于执行脚本的 bash 环境里，`gmt` 必须可用（`gmt begin … gmt end` 现代模式）。 |
| **Ghostscript** | GMT 的 `psconvert` 出 PNG/PDF 时需要。 |
| **Python 3.10+** | 运行源码或打包。 |
| **bash** | 用于执行 GMT 脚本。Windows 上推荐 **Git for Windows** 自带的 bash；macOS / Linux 自带。 |
| **WebView2 运行时** | 仅 Windows 桌面程序需要（系统通常已自带）。 |

> Windows 提示：把 GMT 的 `bin` 目录加进 Git Bash 的 PATH（或 `gmt.exe` 所在目录），并确保 `gmt`、`gswin64c`（Ghostscript）可被 bash 调用。

---

## 快速开始

### 方式一：下载预编译程序（推荐）

到仓库的 **Releases** 页面下载，提供两种形态：

- **`GMT-VectorLab.exe`（直接运行版 / 便携）**：单文件，双击即运行，无需安装，可放进任意目录或 U 盘。
- **`GMT-VectorLab-Setup.exe`（可安装版）**：双击安装到 `%LOCALAPPDATA%\Programs\GMT-VectorLab`（无需管理员权限），自动在开始菜单与桌面创建快捷方式，并提供卸载入口。

两者内嵌的应用完全相同。运行仍需本机有 **GMT 6 + Ghostscript** 才能出图（仅查看/编辑/导出图件不需要）。

### 方式二：从源码运行

```bash
git clone https://github.com/kekered224/GMT-VectorLab.git
cd GMT-VectorLab
pip install -r requirements.txt

# 直接跑桌面程序（工作目录默认定位到 examples/ 时，会加载示例脚本）
python app.py
```

也可以先用命令行体验命令级流程（无需桌面环境）：

```bash
python gmt_editor.py parse   --script examples/plot.sh --json ir.json     # 脚本 -> 结构化 IR
python gmt_editor.py report  --script examples/plot.sh --overlay examples/overlay.json
python gmt_editor.py render  --script examples/plot.sh --overlay examples/overlay.json  # 叠加并重渲染出图
python gmt_editor.py verify  --script examples/plot.sh                     # 源脚本 sha256 校验
```

---

## 使用步骤

1. **打开脚本**：启动后点右上角「打开脚本」，选择你的 GMT 脚本（含 `gmt begin … gmt end` 的 `.sh`）。脚本所在目录成为工作目录。
2. **命令模式（可选）**：在左侧勾选图层、修改选项，点「渲染」即时预览——源脚本本身不会被改动。
3. **画布模式**：切到画布，点选元素后用手柄拖拽 / 缩放 / 旋转，双击文字编辑内容。
4. **导出**：点「导出」，选 **PNG**（默认最高画质）或 **JPG**（填 DPI），保存到本地。

> 工作目录约定：程序默认读取当前目录下的 `plot.sh`，也可用环境变量 `GMT_SCRIPT` 指定脚本名、`GMT_WORK` 指定工作目录。

---

## 示例

`examples/` 目录包含一个开箱即用的示例：

- `plot.sh` —— 南中国海站点分布图（源脚本，**只读真源**）。
- `stations.dat` / `stations_lab.dat` —— 站点坐标与标注数据。
- `overlay.json` —— 命令级改动示例（改范围、配色、符号），演示“脚本不动、只叠 overlay”。

把 `examples/` 作为工作目录打开 `plot.sh`，即可看到命令级 overlay 的效果；切到画布模式还能直接拖拽站点符号、改标注文字。

---

## 从源码打包成单文件程序

**直接运行版（便携 exe）：**

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller GMT-VectorLab.spec
```

产物在 `dist/GMT-VectorLab`（Windows 为 `.exe`）。`GMT-VectorLab.spec` 已配好图标、版本信息与资源内联（ui.html / fieldkit.js / canvaskit.js 会被打包进单文件）。

**可安装版（Setup exe）：**

```bash
# 1) 先按上一步产出直接运行版 GMT-VectorLab.exe
# 2) 把它复制到 packaging/ 目录
cp dist/GMT-VectorLab/GMT-VectorLab.exe packaging/
# 3) 打包安装器 (内嵌上面的 exe, 运行时解压 + 建快捷方式 + 卸载脚本)
pyinstaller packaging/GMT-VectorLab-Setup.spec
```

安装器默认安装到 `%LOCALAPPDATA%\Programs\GMT-VectorLab`，无需管理员权限。

---

## 项目结构

```
GMT-VectorLab/
├─ app.py              桌面程序入口（pywebview）；可打包为单文件程序
├─ core.py             共享内核：渲染入口、产物定位、画布缓存
├─ gmt_editor.py       引擎：脚本解析、overlay 叠加、直跑渲染、哈希守护
├─ svgify.py           PDF → 可寻址 SVG（画布编辑的数据源）
├─ reapply.py          元素 overlay 烘焙回 PDF/PNG
├─ ui.html             前端界面（画布模式 / 命令模式）
├─ canvaskit.js        画布交互：拖拽、缩放、旋转、多选、文字编辑
├─ fieldkit.js         GMT 选项 → 表单控件的解析规则
├─ GMT-VectorLab.spec   PyInstaller 配置（直接运行版）
├─ packaging/           可安装版（Setup.exe）的构建源码与 spec
├─ icon.ico            程序图标
├─ version_info.txt    Windows 版本信息资源
└─ examples/           示例脚本与数据
```

---

## 已知限制

- **中文标题字体**：GMT 默认字体无 CJK 字形，`+t"中文"` 会花屏。需配置 CJK 字体（`gmt set FONT_TITLE` 指向中文字体或走 `gmt.conf` / LaTeX）。交付图建议先用英文标题。
- **命令级解析假设**：按 shell 惯例“值粘连在 flag 后”（如 `-W0.5p,black`）。若脚本用 `-W 0.5p,black`（flag 与值分离）需扩展解析器。
- **编辑粒度**：命令模式是“图层/命令”级编辑；画布模式是“元素”级编辑。两者都不依赖把脚本拆成“点中某根轴/某个刻度”的像素级命中。

---

## License

[MIT](LICENSE)
