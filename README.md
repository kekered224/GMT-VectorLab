# GMT VectorLab

> 画布式 GMT 改图工具 —— 不改你的源脚本，直接在原图上拖拽、缩放、旋转、改文字，并高清导出。

GMT（Generic Mapping Tools）是地学制图的业界标准，主要用于**地质、地球物理、海洋、大气与行星科学**：海岸线底图、地形/重力/磁异常网格、地震震源机制（meca）、剖面图与站点分布图，论文里的出版级插图大多出自它。但它的渲染是“命令 → 图像”的无状态流程：一旦出图，**没有可点选的对象场景图**，想微调一个标题、挪一下站点符号，只能回去改脚本、重跑。

现在多数脚本由 AI 生成。第一版通常能用，但离出版还差最后一点：字号、图例位置、配色、标注排布 —— 这些用对话交代不清，只能一轮轮改，而每改一处就要整图重画一次，时间和 token 都花在重画上。

GMT VectorLab 的分工很明确：**AI 出出版级底稿，你来定终版**。

GMT VectorLab 在这一点上补了一层可视化编辑：

- **命令级 overlay**：把源脚本解析成结构化图层，你的所有微调写进独立的 `overlay.json`，重渲染时叠加。**源脚本永远只读**（每次渲染前后比对 sha256 强校验）。
- **画布级编辑**：把 GMT 出的 PDF 重建为“每个元素独立可寻址、文字仍是真文字”的 SVG，在画布上**点选 / 拖拽 / 缩放 / 旋转 / 改文字**，还能自己**加点、连折线、画多边形**，支持多选、撤销重做。
- **高清导出**：一键导出 **PNG**（最高画质）或 **JPG**（自定义 DPI，默认 300，科研绘图建议 ≥300）。
- **长渲染可控**：单次渲染超过 **2 分钟**会弹出提示并实时显示已用时间，可选「继续等待」或「取消这次渲染」；取消只结束 GMT 进程（连同其子进程），不动你的脚本，界面立即恢复。单次渲染硬上限 30 分钟。

整个工具是一个原生桌面窗口（pywebview + WebView2），不开浏览器、不占端口。

---

## 特性一览

- 打开任意 GMT 脚本（任意文件名、任意位置），其所在目录即工作目录。
- 两种编辑模式：
  - **命令模式**：勾选图层、改选项（如 `-R`、`-W`、`-G`），立即重渲染。
  - **画布模式**：在渲染出的图上直接拖拽元素；拖角自由缩放（按住 **Shift** 等比）、拖边单轴拉伸（PPT 式手感）、拖顶部旋转；双击改文字；顶部「插入」把文本框、点、折线、多边形和 10 余种预设形状（矩形、圆角矩形、椭圆、三角形、菱形、五边形、六边形、星形、箭头、双向箭头、平行四边形）放在一个菜单里；折线/多边形按住 **Shift** 约束水平/竖直/45°，**Ctrl+拖动**复制元素。
- 源脚本只读守护：任何改动都不写回源脚本，只存为 overlay。
- **多画布**：脚本里有多个 `gmt begin … gmt end` 时，每张图各占一个画布，可逐张切换编辑，元素改动互不串图。
- **工程文件**：命令级改动 + 每张画布的元素改动保存为 `.gvlproj`，下次打开继续编辑。
- 导出图片（PNG / JPG），JPG 按 DPI 设定分辨率。
- **元素浏览器**：左栏统一列出文字、矢量与自绘形状，支持按类型筛选、搜索、显隐、双击改名；右键（或行尾「⋯」）可**复位变换 / 重命名 / 缩放到元素 / 复制 / 删除**。画布中 **Shift/Ctrl+点击**可多选，选中项会自动滚动并高亮到左栏；右键画布元素直接弹出同一菜单。复位只作用于选中的元素，不会影响其他图层；分区与属性面板都可折叠，元素多时列表内部滚动。
- **主题**：右上角可切换浅色 / 深色 / 跟随系统，设置自动记住。

---

## 环境要求

**下载预编译版（推荐）**：无需安装 GMT、Ghostscript 或 Git —— 程序内置完整运行时（GMT 6.7 + Ghostscript 10.07 + bash），双击即用。只需 Windows 10/11（系统一般已自带 WebView2）。

**从源码运行 / 自行打包**：需要 **GMT 6.x**、**Ghostscript**、**bash**（Windows 推荐 Git for Windows 自带）与 **Python 3.10+**。

内置运行时包含以下组件（解压约 420 MB）：

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| [GMT](https://www.generic-mapping-tools.org/) | 6.7.0 | 渲染引擎 |
| Ghostscript | 10.07（随 GMT 官方包） | PDF / PNG 输出 |
| GDAL / PROJ / FFmpeg | 随 GMT 官方包 | 数据与格式支持 |
| MinGit bash | 2.56.0.4 | 执行 `gmt begin … gmt end` 脚本 |

> 内置运行时只作用于程序自己的子进程：不改注册表、不改系统 PATH。机器上已经装了 GMT 的用户可以照常用自己的版本，两者不会冲突；内置版始终优先使用自带的那一份。

---

## 快速开始

### 方式一：下载预编译程序（推荐）

到仓库的 [Releases](https://github.com/kekered224/GMT-VectorLab/releases/latest) 页面下载，提供四种形态：

| 下载项 | 说明 |
| --- | --- |
| `GMT-VectorLab-Example-<版本>.zip` | **内置运行时 · 示例版**：解压后双击 `启动示例.bat`，直接打开南中国海站点图。第一次使用推荐这个。 |
| `GMT-VectorLab-Portable-<版本>.zip` | **内置运行时 · 便携版**：解压后双击 `GMT-VectorLab.exe`，再打开自己的脚本。不写注册表，可放 U 盘。 |
| `GMT-VectorLab-Setup.exe` | **内置运行时 · 安装版**：双击安装到 `%LOCALAPPDATA%\Programs\GMT-VectorLab`（无需管理员权限；用户名含中文时自动装到 `C:\Users\Public\GMT-VectorLab`），自动创建开始菜单/桌面快捷方式与卸载入口。 |
| `GMT-VectorLab.exe` | **轻量版**：单文件，仅适合本机已装好 GMT 6 + Ghostscript 的用户。 |

内置运行时版本开箱即用，**不需要**再装 GMT / Ghostscript / Git；轻量版与源码运行仍需本机具备 GMT 环境。各资产的 SHA-256 见同一 Release 的 `SHA256SUMS.txt`。

### 换一台电脑跑示例（三步）

1. 复制 `GMT-VectorLab-Example-<版本>.zip` 到目标电脑（U 盘 / 网盘均可，约 270 MB，解压后约 480 MB）。
2. 解压到任意目录 —— **路径含中文也可以**，程序会自动映射到 ASCII 目录联接供 GMT 读取。
3. 双击 `启动示例.bat`（等价于双击 `GMT-VectorLab.exe`，示例脚本与数据就在同一目录）。

首次运行若被 Windows SmartScreen 拦截，点「更多信息 → 仍要运行」；若提示缺少 WebView2，安装一次 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) 即可（Windows 11 与多数 Windows 10 已自带）。

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
3. **画布模式**：切到画布，点选元素后用手柄拖拽 / 缩放 / 旋转，双击文字编辑内容。点顶部「插入」→ 文本框可放文字；点 / 折线 / 多边形连续落点，双击或 **Enter** 完成，**Esc** 取消；预设形状按住拖拽绘制（**Shift** 画正方形/正圆，单击给默认大小）。折线/多边形绘制时按住 **Shift** 约束水平/竖直/45°；**Ctrl+拖动**元素可原地复制。画布中 **Shift/Ctrl+点击**可多选（Ctrl 纯点击不会复制，拖过 5px 才是复制拖动），选中项会高亮并自动滚动到左栏；右键画布元素直接弹出菜单，右栏也有「删除」按钮，**Delete** 键同样可用。左栏「元素」列出文字、矢量与自绘形状，可筛选、搜索、显隐、双击改名；右键菜单可复位变换、重命名、缩放到元素、复制或删除（原 GMT 元素删除 = 导出时隐藏，自绘/副本为真正移除）；右侧属性面板按「位置/变换、文字样式、矢量样式」分组，可折叠。
4. **多画布**：脚本里有多个 `gmt begin … gmt end` 时，左侧「画布 · 图件」会列出每张图；点条目切换，每张图的元素改动独立保存。
5. **保存工程**：点顶部「保存工程」写入 `.gvlproj`（命令级改动 + 所有画布的元素改动 + 脚本位置）。下次点「打开工程」会自动切回对应脚本并恢复全部改动；源脚本若已变化会给出提示。
6. **导出图片**：点「导出图片」，选 **PNG**（默认最高画质）或 **JPG**（填 DPI），保存到本地。

> 「保存工程」保存的是**可继续编辑的源数据**（不含成品图）；「导出图片」把当前改动烘焙成**成品图**，不能再编辑。需要接着改就用前者，需要交图就用后者。

> 工作目录约定：程序默认读取当前目录下的 `plot.sh`，也可用环境变量 `GMT_SCRIPT` 指定脚本名、`GMT_WORK` 指定工作目录。

---

## 示例

`examples/` 目录包含一个开箱即用的示例：

- `plot.sh` —— 南中国海站点分布图（源脚本，**只读真源**）。
- `stations.dat` / `stations_lab.dat` —— 站点坐标与标注数据。
- `overlay.json` —— 命令级改动示例（改范围、配色、符号），演示“脚本不动、只叠 overlay”。

把 `examples/` 作为工作目录打开 `plot.sh`，即可看到命令级 overlay 的效果；切到画布模式还能直接拖拽站点符号、改标注文字。

---

## 从源码打包

以下步骤都在仓库根目录执行（Windows）。

### 1. 轻量版单文件程序

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller GMT-VectorLab.spec
```

产物为 `dist/GMT-VectorLab.exe`。`GMT-VectorLab.spec` 已配好图标、版本信息与资源内联（ui.html / fieldkit.js / canvaskit.js 会被打包进单文件）。此版本**不含**运行时，要求本机已装 GMT 6 + Ghostscript。

### 2. 组装内置运行时

```bash
python packaging/build_runtime.py
```

脚本只用标准库，自动从官方 Release 下载、解压并组装：

| 组件 | 来源 | 组装位置 |
| --- | --- | --- |
| GMT 6.7.0 win64（含 Ghostscript / GDAL / PROJ / FFmpeg） | [GenericMappingTools/gmt](https://github.com/GenericMappingTools/gmt/releases/tag/6.7.0) | `runtime/gmt` |
| MinGit 2.56.0.4（提供 bash） | [git-for-windows/git](https://github.com/git-for-windows/git/releases/tag/v2.56.0.windows.4) | `runtime/bash` |

完成后会做完整性校验，并生成 `packaging/runtime.zip`（zip 内直接是 `gmt/` 与 `bash/`，不含外层 `runtime/`）。

| 参数 | 作用 |
| --- | --- |
| `--gmt-zip` / `--mingit-zip` | 使用已下载的本地官方包，跳过下载 |
| `--no-zip` | 只组装 `runtime/`，不生成 `runtime.zip` |
| `--force` | 忽略缓存，重新下载解压 |
| `--runtime` / `--zip` | 自定义运行时目录 / 压缩包路径 |

### 3. 内置运行时便携版

```bash
dist/GMT-VectorLab-Portable/
├─ GMT-VectorLab.exe     # 第 1 步产物
└─ runtime/              # 第 2 步产物
   ├─ gmt/
   └─ bash/
```

程序启动时优先使用同目录（或上级目录）的 `runtime/`，找不到才回落到系统 GMT；整个目录压缩即可分发。

### 4. 安装版 Setup

```bash
# 1) 先产出 dist/GMT-VectorLab.exe（第 1 步）
copy dist\GMT-VectorLab.exe packaging\
# 2) 生成 packaging\runtime.zip（第 2 步默认输出到这里）
python packaging\build_runtime.py
# 3) 打包安装器：内嵌 exe 与 runtime.zip，安装时解压 + 建快捷方式 + 写卸载项
pyinstaller packaging\GMT-VectorLab-Setup.spec
```

安装器默认安装到 `%LOCALAPPDATA%\Programs\GMT-VectorLab`（无需管理员权限）；用户名含中文时自动改到 `C:\Users\Public\GMT-VectorLab`，避开 GMT 的窄字符路径问题。

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
├─ GMT-VectorLab.spec   PyInstaller 配置（轻量版单文件程序）
├─ packaging/           安装版与内置运行时的构建
│  ├─ build_runtime.py   下载官方 GMT / MinGit，组装 runtime/ 并生成 runtime.zip
│  ├─ installer.py       安装器：解压运行时、建快捷方式与卸载项
│  └─ GMT-VectorLab-Setup.spec
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
