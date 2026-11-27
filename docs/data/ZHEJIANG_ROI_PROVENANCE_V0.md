# 浙江三湾 ROI 边界来源与派生报告 v0（M2.1a / Issue #7）

- 状态：**PROVISIONAL — 三湾全部为 Tier-C 确定性派生几何，非官方边界**
- 访问日期：2026-10-01（所有 VERIFIED 来源均于该日实际打开/读取）
- 配置：[configs/data/zhejiang_multibay_m21a.yaml](../../configs/data/zhejiang_multibay_m21a.yaml)
- 产物：
  - [datasets/manifests/zhejiang_roi_registry_v0.csv](../../datasets/manifests/zhejiang_roi_registry_v0.csv) / `.parquet`
  - [datasets/manifests/zhejiang_roi_source_audit_v0.csv](../../datasets/manifests/zhejiang_roi_source_audit_v0.csv)
  - [datasets/manifests/zhejiang_roi_anchor_snaps_v0.csv](../../datasets/manifests/zhejiang_roi_anchor_snaps_v0.csv)
  - [datasets/rois/zhejiang_bays_v0.geojson](../../datasets/rois/zhejiang_bays_v0.geojson)（LGPL 归属声明内嵌）
- 代码：[src/spartina/data/zhejiang/rois.py](../../src/spartina/data/zhejiang/rois.py)、
  [scripts/data/zhejiang/build_roi_registry.py](../../scripts/data/zhejiang/build_roi_registry.py)

## 1. 结论：不存在可下载的官方权威三湾矢量

对政府门户、自然资源部文件、浙江省规划文件与公开数据库的检索结论：

1. 三湾的官方边界均以**文字定义**存在（“口门连线”“连线向湾内一侧封闭海域”），
   未发现任何一级政府发布的、可公开下载的海湾行政/地理边界矢量（Shapefile/GeoJSON）。
2. 县级海域勘界/海岸线保护矢量未公开；《浙江省海洋功能区划（2011-2020，2018修订）》
   《浙江省海岸线保护与利用规划（2016-2020）》提供文本、登记表与图件，后者图件声明
   CGCS2000，但**无可再分发的矢量数据与下载渠道**（渠道状态 UNKNOWN）。
3. 因此三湾 ROI 均不能达到 Tier-A（官方矢量）或 Tier-B（带清晰出处的公开数据集边界），
   本阶段统一以 **Tier-C：确定性派生** 交付，并在所有产物中标注
   `PROVISIONAL_TIER_C_DERIVED`。派生结果不得在论文或产品中表述为“官方边界”。

## 2. 方法（完全确定、可复现）

1. **基底岸线（固定版本+校验和）**：GSHHG v2.3.7 high resolution L1（海陆分界多边形），
   WGS84(EPSG:4326)，zip SHA256
   `8dbbe7e071e77e9e75f2d639239099ebca8d5c16d6a07df8169729d49f15cf41`，
   L1 shp SHA256
   `d870bdbc90a074f87a8c09a9630abb5f18916314b9a196dba2e6866fd51ef325`。
   许可 LGPL-3.0-or-later（允许附版权声明再分发）；引用 Wessel & Smith (1996),
   DOI [10.1029/96JB00104](https://doi.org/10.1029/96JB00104)。
   GSHHG 是**平均岸线近似**；三湾均为强潮海湾，瞬时岸线在潮周期内可摆动数公里，
   故派生水面面积**不是**海图基准下的法定海域面积。
2. **地名锚点→岸线顶点吸附**：SECTION_POINT 锚点（岬角/口门岛）在配置中给出近似经纬度与
   显式吸附半径（m），构建时在全部 GSHHG L1 多边形外环顶点中取大圆距离最近者；
   确定性 tie-break：多边形在文件中的顺序→顶点序。超半径直接报错（禁止静默移动）。
   每次吸附的请求点、命中点与偏差（m）写入 anchor_snaps 清单。
3. **陆上闭合角**（CONSTRUCTION_CORNER）：湾顶包络用两个陆上闭合点收口，使用前断言
   该点被 GSHHG 陆地多边形覆盖，避免把闭合线放到海上。
4. **水面与陆上带**：`包络多边形 − 陆地 = 水面`；再将水面在 EPSG:32651 下缓冲 2000 m
   （mitre join），与包络内陆地求交得到**向陆 2 km 纳入带**（覆盖潮间带/互花米草生境带）；
   `ROI = 水面 ∪ 纳入带`。几何无效时仅允许 shapely `make_valid` 修复并在 registry 标记
   （本次三湾均未触发修复）。
5. 岛链口门采用**直线段连接**（简化自李加林等 2020 引《中国海湾志》的“顺岛屿向海一侧
   岸线连接”原则），v0 明确声明该简化，留待 v1 沿岛屿岸线精化。
6. **指纹**：几何指纹=坐标保留 6 位小数后规范化 GeoJSON 的 SHA-256；
   逻辑指纹=registry 行（除指纹列）规范化 JSON 的 SHA-256。同输入重跑逐字节一致（已验证）。

复现：

```bash
# 1) 下载基底（字节不入库）
mkdir -p work/sources && cd work/sources
curl -fsSL -o gshhg-shp-2.3.7.zip \
  http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip
unzip gshhg-shp-2.3.7.zip "GSHHS_shp/h/*" LICENSE.TXT COPYING.LESSERv3
# 2) 校验 sha256（见上）后构建
conda activate spartina-earth
python scripts/data/zhejiang/build_roi_registry.py
```

## 3. 逐湾结果与出处

### 3.1 ZJ-HZB 杭州湾

- 状态：PROVISIONAL / Tier-C；几何有效；几何指纹
  `7b096186ac5238ef7ff8c479fdc84be263ddd0cc99cd7127540c29e2ce476f00`
- 口门定义（VERIFIED 文字）：东岸口门为**南汇嘴（芦潮港）—镇海口（甬江口·扬子角）连线**；
  与钱塘江河口区分界采用**澉浦（长山闸）—西三闸断面**（余祈文等 1994，PROVISIONAL，
  卷期/页码 TODO_VERIFY）。
- 吸附记录：南汇嘴 7307 m（GSHHG 该段岸线早于近期南汇围垦，命中点在现岬角以西约 8 km，
  已在配置注释声明）；镇海口 158 m；西三闸 2957 m；澉浦 713 m。
- 面积 QA：派生水面 **4132.0 km²**、陆上带 199.9 km²、ROI 4331.9 km²（包络 4801.9 km²）；
  通行文献“约 5000 km²”为 −17.4%。差异原因（未进一步归因）：平均岸线 vs 海图/理论深度
  基准、口门与西界断面选取、围垦岸线年代差异。**5000 km² 仅作 sanity check，不做校验目标。**
- 负证据（VERIFIED）：海预减字[2017]7号预报海区体系中杭州湾**无单一海区单元**（被拆分），
  与三门湾 E44、乐清湾 E52 不同，保留该事实。

### 3.2 ZJ-SMB 三门湾

- 状态：PROVISIONAL / Tier-C；几何有效；几何指纹
  `e2a68b98106c2ddb256785097020b315901b5832b8e1ede978add7c70adc22f9`
- 口门定义（VERIFIED 原文）：三门县人民政府《自然地理》页（2026-04-13 更新）：
  “湾口面向东南，以**金柒门—三门岛—牛头山的连线**为界与东海相连。湾口宽 22 公里，
  湾口至湾底纵长 42 公里……低潮总面积 390 余平方公里，海岸线长 303 公里，海域面积达
  775 平方公里。” URL:
  <https://www.sanmen.gov.cn/art/2025/6/26/art_1229679902_59040617.html>
- 吸附：金柒门 3630 m；三门岛 96 m；牛头山 529 m。湾顶包络角取 121.40°E 陆上点，
  较研究区文献 bbox 西界 121°25′(121.417°E) 再西移约 1.7 km，保证湾顶最西水面
  （GSHHG 实测约 121.445°E）不被切断。
- 面积 QA：派生水面 **706.0 km²**（vs 官方海域 775，−8.9%）；陆上带 638.1 km²，
  ROI 1344.1 km²（该湾枝状港汊与岛礁众多、岸线 303 km，陆上带相应较大）。
- **保留分歧**：口门宽度另有约 14 海里（约 26 km）的百科级说法；本阶段不选取、不调和，
  与官方 22 km 并列保留。研究区文献 bbox（Si Han et al. 2019,
  DOI [10.15244/pjoes/87106](https://doi.org/10.15244/pjoes/87106)，
  28°57′–29°22′N、121°25′–121°58′E）为研究区而非官方边界，仅作交叉参照。
- 同页潮情文字（平均潮差 4.25 m、最大 7.75 m）供潮位策略文档引用，不用于本几何。

### 3.3 ZJ-YQB 乐清湾

- 状态：PROVISIONAL / Tier-C；几何有效；几何指纹
  `b42ca18b97597be94792b99680a9c190cfa73215d9ada40af4f991ad859041cd`
- 口门与范围（VERIFIED 原文）：乐清市府办《乐清湾“一湾一策”……行动方案》
  （乐政办发〔2021〕20号）：“北起乐清湾底，南至口门的**乐清市黄华岐头咀**至乐清与
  洞头区和玉环市的海上分界线……”坐标 27°58′56″–28°23′16″N、
  120°57′29″–121°12′22″E。**该 bbox 仅覆盖乐清市管辖片，不是全湾边界**——全湾向
  NE 延伸至温岭侧湾顶、向 SE 含大门岛/小门岛/鹿西岛链，本派生按全湾构造。
  URL（目录页）：<https://www.yueqing.gov.cn/col/col1229276916/index.html>
- 自然资源部 E52 单元（VERIFIED）：“乐清湾口连线向湾内一侧的封闭海域」，
  <https://gc.mnr.gov.cn/201806/t20180614_1795770.html>。
- 吸附：小门 339 m；大门岛 1563 m；鹿西岛 1072 m。
- 面积 QA：派生水面 **446.3 km²**（vs 通行全湾值 463.6 km²，−3.7%；该值一手出处
  UNKNOWN，TODO_VERIFY，仅作 sanity check）；陆上带 133.3 km²，ROI 579.6 km²。

## 4. 已知限制（全部显式保留，不做静默处理）

1. 基底为**平均岸线**：三湾潮差大（三门湾平均 4.25 m/最大 7.75 m；杭州湾澉浦涌潮段
   量级更大），潮间带在低潮时出露数百平方公里（三门湾官方低潮面积 390+ km²）；
   潮间带覆盖策略另见潮位文档，v0 以“水面+2 km 陆上带”工程化覆盖，不声称等同生境范围。
2. 官方坐标系为 CGCS2000（浙江规划文本声明）；GSHHG 为 WGS84，v0 分析投影统一
   EPSG:32651。WGS84/CGCS2000 在该区域米级差异不影响本阶段尺度，跨基准精确套合留待 v1。
3. 南汇嘴段 GSHHG 岸线年代偏旧（~8 km 偏差已记录）；杭州湾西界断面文献为 PROVISIONAL。
4. 岛链按直线段连接，未沿岛屿向海一侧岸线；湾顶陆上闭合角为工程点而非地名点。
5. 全部面积比较仅为 sanity check；没有任何派生面积被用作科学结论。
6. OSM 岸线仅作交叉核对备选（ODbL 传染风险），本 v0 **未使用**。

## 5. 来源状态总表（详见 source audit CSV）

| source_id | 类型 | 状态 | 关键内容 |
|---|---|---|---|
| src_hzb_text_igsnrr | 文献文字 | VERIFIED | 杭州湾口门连线、约5000 km²；URL UNKNOWN |
| src_hzb_section_yu1994 | 文献文字 | PROVISIONAL | 澉浦-西三断面；卷期 TODO_VERIFY |
| src_smb_gov_geography | 县政府门户 | VERIFIED | 金柒门-三门岛-牛头山；775/22/42/303/390+ |
| src_smb_sihan2019 | OA 期刊 | VERIFIED | 研究 bbox（非官方边界） |
| src_yqb_ywyc2021 | 市府办文件 | VERIFIED | 乐清管辖片 bbox+口门地名；非全湾 |
| src_yqb_published_463 | 通行数值 | PROVISIONAL | 463.6 km² 一手出处 UNKNOWN |
| src_mnr_forecast_units | 部委文件 | VERIFIED | E44/E52；HZB 无单一单元 |
| src_bay_method_li2020 | 期刊方法 | VERIFIED | 岬角连线/岛链原则 |
| src_gshhg | 矢量岸线 | VERIFIED | LGPL，版本+校验和固定 |
| src_zj_marine_function_2012r2018 | 省规划 | VERIFIED | 文本已读、无矢量 |
| src_zj_coastline_protection_2016 | 省规划 | VERIFIED | 文本已读、CGCS2000、无矢量 |

## 6. 后续（不在 M2.1a 执行）

- v1 候选精化：岛链沿岸线连接、南汇嘴段更新岸线基底或引入更高分辨率数据源
  （需先确认许可）、官方勘界矢量获取尝试（渠道 UNKNOWN，不承诺可得）。
- 任何 Tier-A/Tier-B 升级必须替换几何指纹并重跑全部下游清单，旧指纹保留不删。
