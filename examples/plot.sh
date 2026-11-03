#!/usr/bin/env bash
# ============================================================
# 源脚本 (SOURCE OF TRUTH) —— 绝对唯一真源
# GMT VectorLab 只 *读取* 本文件，绝不写回。所有微调都存进
# 同目录下的 overlay.json，重渲染时叠加，脚本本身保持原样。
# ============================================================
gmt begin figure png,pdf
    gmt coast -R110/122/2/22 -JM12c -Baf -BWSen+t"South China Sea" -W0.5p,black -Ggray20 -Sazure3 -Na
    gmt plot stations.dat -St0.35c -Gred3 -W0.5p,white
    gmt text -F+f8p,Helvetica-Bold,black+jLM -D0.15c/0c -N stations_lab.dat
gmt end show
