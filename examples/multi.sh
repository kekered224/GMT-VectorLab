#!/usr/bin/env bash
# ============================================================
# 多画布示例: 一个脚本里有两个 gmt begin/end 会话, 各出一张图。
# GMT VectorLab 会把它们列成两个画布, 逐张切换编辑, 改动互不串图。
# ============================================================
# 图 1: 南中国海站点地图 (墨卡托投影)
gmt begin scs_map png,pdf
    gmt coast -R110/122/2/22 -JM12c -Baf -BWSen+t"South China Sea" -W0.5p,black -Ggray20 -Sazure3 -Na
    gmt plot stations.dat -St0.35c -Gred3 -W0.5p,white
    gmt text -F+f8p,Helvetica-Bold,black+jLM -D0.15c/0c -N stations_lab.dat
gmt end

# 图 2: 同一批站点的经纬度散点 (笛卡尔投影)
gmt begin stations_xy png,pdf
    gmt plot stations.dat -R110/122/2/22 -JX12c/9c -Baf -BWSen+t"Stations (lon-lat)" -St0.5c -Gdodgerblue -W0.7p,white
gmt end
