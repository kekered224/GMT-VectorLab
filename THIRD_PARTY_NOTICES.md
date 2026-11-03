# 第三方组件声明（内置运行时）

GMT VectorLab 应用本体采用 MIT 许可证（见 [LICENSE](LICENSE)）。
“内置运行时”版本随程序一起分发下列第三方软件，它们各自保留原有许可证：

| 组件 | 随附版本 | 许可证 | 源码 / 说明 |
| --- | --- | --- | --- |
| GMT（Generic Mapping Tools） | 6.7.0 | LGPL-3.0-or-later | https://github.com/GenericMappingTools/gmt |
| Ghostscript | 10.07.0 | AGPL-3.0-or-later | https://github.com/ArtifexSoftware/ghostscript |
| GDAL | GMT 官方包随附 | MIT | https://github.com/OSGeo/gdal |
| PROJ | GMT 官方包随附 | MIT | https://github.com/OSGeo/PROJ |
| FFmpeg（GMT movie 模块用） | GMT 官方包随附 | LGPL-2.1-or-later（以官方构建为准） | https://ffmpeg.org |
| MinGit / Git for Windows（内置 bash） | 2.56.0.4 | GPL-2.0 | https://github.com/git-for-windows/git |

完整许可证文本位于运行时目录中：

- `runtime/gmt/share/doc/copying/COPYINGv3`（GPL-3）
- `runtime/gmt/share/doc/copying/COPYING.LESSERv3`（LGPL-3）
- `runtime/gmt/share/doc/copying/COPYING.AGPLv3`（AGPL-3，Ghostscript）
- `runtime/gmt/share/doc/copying/LICENSE.TXT`（GMT 总说明）
- `runtime/gmt/share/GDAL_DATA/LICENSE.TXT`（GDAL）
- `runtime/bash/LICENSE.txt`（Git for Windows / MinGit）

GMT 的 Windows 官方发行包本身即包含上述依赖（Ghostscript、GDAL、PROJ、FFmpeg），
本项目只做原样再分发，未修改其二进制。各组件源码可从表中链接获取。
