# 示例：南中国海站点分布图

本目录是一个开箱即用的 GMT VectorLab 示例。

## 文件

- **`plot.sh`** —— 源脚本（**唯一真源，只读**）。用 GMT 现代模式画一张南中国海站点分布图：
  - `gmt coast` 海岸线 / 填充 / 边框
  - `gmt plot` 站点符号
  - `gmt text` 站点标注
- **`stations.dat`** —— 站点坐标（经度 纬度），每行一个点。
- **`stations_lab.dat`** —— 站点标注（经度 纬度 名称）。
- **`overlay.json`** —— 命令级改动示例：放大范围、改海岸线配色与线宽、把站点符号换成方块并改色。**演示“脚本不动、只叠 overlay”**。
- **`multi.sh`** —— 多图脚本示例：一个脚本里两个 `gmt begin … gmt end`，分别出 `scs_map` 与 `stations_xy` 两张图。
- **`multi_overlay.json`** —— 多图命令级改动示例：只改第二张图的站点符号（全局序号 3），第一张图不受影响。

## 怎么用

1. 启动 GMT VectorLab，点「打开脚本」，选择本目录下的 `plot.sh`。
2. 直接渲染即可看到原图。
3. 在**命令模式**下加载 `overlay.json`（或手动改选项），点「渲染」——源脚本 `plot.sh` 内容不变，仅叠加改动。
4. 切到**画布模式**，可拖拽站点符号、改标注文字、缩放旋转元素。
5. 点「导出」保存 PNG / JPG。

### 多画布 / 工程文件

1. 点「打开脚本」，选择 **`multi.sh`**。
2. 左侧「画布 · 图件」会列出 `scs_map` 与 `stations_xy`；点条目切换，每张图的元素改动独立保存。
3. 点顶部「保存工程」写入 `.gvlproj`；下次点「打开工程」会自动切回该脚本并恢复所有画布改动。

## 命令行验证（无需桌面环境）

```bash
# 脚本 -> 结构化 IR
python ../gmt_editor.py parse   --script plot.sh --json ir.json

# 查看 overlay 相对源脚本的改动 diff
python ../gmt_editor.py report  --script plot.sh --overlay overlay.json

# 叠加 overlay 并重渲染出图（figure.png / figure.pdf）
python ../gmt_editor.py render  --script plot.sh --overlay overlay.json

# 校验源脚本 sha256（确认“脚本不动”）
python ../gmt_editor.py verify  --script plot.sh
```

> 前提：本机已安装 GMT 6.x 与 Ghostscript，并在执行脚本的 bash 环境中可用（`gmt`、`gswin64c` 等）。
