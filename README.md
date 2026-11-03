# GMT VectorLab

> 画布式 GMT 改图工具 —— 不改你的源脚本，直接在原图上拖拽、缩放、旋转、改文字，并高清导出。

GMT（Generic Mapping Tools）是地学制图的业界标准，主要用于**地质、地球物理、海洋、大气与行星科学**：海岸线底图、地形/重力/磁异常网格、地震震源机制（meca）、剖面图与站点分布图，论文里的出版级插图大多出自它。但它的渲染是“命令 → 图像”的无状态流程：一旦出图，**没有可点选的对象场景图**，想微调一个标题、挪一下站点符号，只能回去改脚本、重跑。

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

**下载预编译版（推荐）**：无需安装 GMT、Ghostscript 或 Git —— 程序内置完整运行时（GMT 6.7 + Ghostscript 10.07 + bash），双击即用。只需 Windows 10/11（系统一般已自带 WebView2）。

**从源码运行 / 自行打包**：需要 **GMT 6.x**、**Ghostscript**、**bash**（Windows 推荐 Git for Windows 自带）与 **Python 3.10+**。

> 内置运行时只作用于程序自己的子进程：不改注册表、不改系统 PATH。机器上已经装了 GMT 的用户可以照常用自己的版本，两者不会冲突；内置版始终优先使用自带的那一份。

---

## 快速开始

### 方式一：下载预编译程序（推荐）

到仓库的 [Releases](https://github.com/kekered224/GMT-VectorLab/releases/latest) 页面下载，提供三种形态：

- **`GMT-VectorLab-Portable.zip`（内置运行时 · 便携版）**：解压后双击 `GMT-VectorLab.exe` 即用，不写注册表、无需安装，可放 U 盘。整个目录一起移动即可。
- **`GMT-VectorLab-Setup.exe`（内置运行时 · 安装版）**：双击安装到 `%LOCALAPPDATA%\Programs\GMT-VectorLab`（无需管理员权限；用户名含中文时自动装到 `C:\Users\Public\GMT-VectorLab`），自动创建开始菜单/桌面快捷方式与卸载入口。
- **`GMT-VectorLab.exe`（轻量版）**：单文件，仅适合本机已装好 GMT 6 + Ghostscript 的用户。

内置运行时版本开箱即用，**不需要**再装 GMT / Ghostscript / Git；轻量版与源码运行仍需本机具备 GMT 环境。

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

**可安装版（Setup exe，内置运行时）：**

```bash
# 1) 先按上一步产出轻量版 GMT-VectorLab.exe
# 2) 把它复制到 packaging/ 目录
cp dist/GMT-VectorLab/GMT-VectorLab.exe packaging/
# 3) 把内置运行时打包成 packaging/runtime.zip（zip 根目录直接是 gmt/ 与 bash/）
#    内置运行时目录结构: runtime/gmt/... + runtime/bash/...
# 4) 打包安装器 (内嵌 exe 与 runtime.zip, 安装时解压 + 建快捷方式 + 卸载脚本)
pyinstaller packaging/GMT-VectorLab-Setup.spec
```

**内置运行时便携版：**

```bash
# 把 dist/GMT-VectorLab/GMT-VectorLab.exe 与 runtime/ 放进同一目录, 整体压缩分发
#   GMT-VectorLab/
#   ├─ GMT-VectorLab.exe
#   └─ runtime/{gmt,bash}
```

安装器默认安装到 `%LOCALAPPDATA%\Programs\GMT-VectorLab`，无需管理员权限。

内置运行时的第三方组件与许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

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
├─ THIRD_PARTY_NOTICES.md  内置运行时的第三方组件与许可证
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
