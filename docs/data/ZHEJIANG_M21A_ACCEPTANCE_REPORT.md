# M2.1a 验收报告：浙江三湾科学采样框架

- Issue：#7 / M2.1a（权威 ROI 出处 + 多年观测普查 + 标签盘点 +
  物候/潮位策略）
- 分支：`reboot/spartina-earth-m0`（仅本地提交，未 push/merge/rebase）
- 报告日期：2026-10-02；GEE 元数据取数：2026-10-01（UTC 时间戳
  逐行记录于 census 表）
- 边界：**只做科学采样框架**。未导出任何影像、未做全湾 GeoTIFF
  下载、未做模型训练、未冻结任何 split/标签/数据集、未开始 M2.1b。

---

## 1. 交付物清单（对照指令 §40）

| 要求 | 实际文件 | 状态 |
|---|---|---|
| config | `configs/data/zhejiang_multibay_m21a.yaml` | ✅ |
| ROI registry csv/parquet | `datasets/manifests/zhejiang_roi_registry_v0.{csv,parquet}` | ✅ |
| 标签盘点 csv/parquet | `datasets/manifests/zhejiang_legacy_label_inventory_v0.{csv,parquet}` | ✅ |
| EO scene census parquet | `datasets/manifests/zhejiang_eo_scene_census_v0.parquet`（678 KB，18,435 行） | ✅ |
| availability | `datasets/manifests/zhejiang_eo_availability_v0.csv`（126 行） | ✅ |
| gap matrix | `datasets/manifests/zhejiang_data_gap_matrix_v0.csv`（1,059 行） | ✅ |
| ROI 出处文档 | `docs/data/ZHEJIANG_ROI_PROVENANCE_V0.md`（+ 同名无 `_V0` 符号链接） | ✅ |
| 标签文档 | `docs/data/ZHEJIANG_LABEL_INVENTORY_V0.md` | ✅ |
| 物候文档 | `docs/data/ZHEJIANG_PHENOLOGY_AND_SEASON_POLICY_V0.md` | ✅ |
| 潮位文档 | `docs/data/ZHEJIANG_TIDE_INUNDATION_POLICY_V0.md` | ✅ |
| holdout 文档 | `docs/benchmark/ZHEJIANG_HOLDOUT_DESIGN_V0.md` | ✅ |
| 验收报告 | 本文件 | ✅ |
| 附加（可追溯性） | `zhejiang_eo_census_summary_v0.{csv,parquet}`（756 组）、`zhejiang_roi_source_audit_v0.csv`、`zhejiang_roi_anchor_snaps_v0.csv`、`datasets/rois/zhejiang_bays_v0.geojson`、`zhejiang_m21a_artifact_fingerprints_v0.csv` | ✅ |

## 2. ROI 结论（Q1–12）

三湾**全部**为 Tier-C 确定性推导边界
（`PROVISIONAL_TIER_C_DERIVED`），不存在可下载的官方海湾矢量：
未发现 ≠ 不存在，状态按 VERIFIED 检索过程 + UNKNOWN 官方矢量如实标注。

| 湾 | 推导水面 km² | 陆上带 km² | ROI km² | 文献值 | 偏差 | 几何指纹（sha256 前 12 位） |
|---|---|---|---|---|---|---|
| ZJ-HZB | 4132.01 | 199.92 | 4331.94 | ~5000 km²（教科书级文字） | −17.36% | `7b096186ac52` |
| ZJ-SMB | 705.99 | 638.09 | 1344.07 | 775 km²（三门县政府网原文） | −8.9% | `e2a68b98106c` |
| ZJ-YQB | 446.26 | 133.29 | 579.55 | 463.6 km²（二手研究值） | −3.74% | `b42ca18b9759` |

- 岸线基准：GSHHG v2.3.7 高分 L1（LGPL-3.0-or-later；Wessel &
  Smith 1996, DOI 10.1029/96JB00104），zip 与 shp 的 sha256 已钉入
  config，重跑字节级一致；
- 口门依据：HZB 南汇嘴—镇海口（西界澉浦—西三为湾-钱塘江口区分界
  断面，出处 PROVISIONAL）；SMB 金柒门—三门岛—牛头山（县政府网
  VERIFIED）；YQB 小门—大门岛—鹿西岛链；
- 岛屿连接按李加林等 2020（地理学报 75(1):126-142,
  DOI 10.11821/dlxb202001010）的"沿海岛向海侧岸线连接"原则做了
  **直线段简化**，偏差已在文档声明；
- 锚点为近似占位坐标，最大吸附距离如实记录（南汇嘴 7,307 m，
  因 GSHHG 岸线早于围垦，已声明）；
- 文献面积仅作 sanity check，不参与几何构造。

## 3. 标签盘点结论（Q13–19，全部为实测交集，非估算）

| 资产 | 年份 | 层级 | ZJ-HZB | ZJ-SMB | ZJ-YQB | 许可 | 允许用途 |
|---|---|---|---|---|---|---|---|
| L1 全国 30 m 栅格（geodata.cn DOI 10.12041/geodata.65372070926827.ver1.db） | 2015 | SILVER | 19,268 像元 / 17.34 km² | 0 | 22,889 像元 / 20.60 km² | 受限，禁止再分发 | VALIDATION_REFERENCE |
| L2 CM-SSM 多边形 | 2020 | WEAK | 0 | 0 | 0 | TODO_VERIFY | DIAGNOSTIC_ONLY |
| L3 杭州湾 mask（c201511839DTSP_2.tif） | ~2015 | WEAK | 15,600 像元 / 14.00 km² | 0 | 0 | 未知 | DIAGNOSTIC_ONLY |
| L4/L5/L6 CMSA 多边形（**已勘误**：非福建，是乐清湾头 121.15–121.22E） | 2019/2020/2021 | WEAK | 0/0/0 | 0/0/0 | 51/158/79 要素（8.82/4.36/9.11 km²） | 未知 | DIAGNOSTIC_ONLY |
| U1–U5 杭州湾 2015 合成体（L8/NDVI/SAI/S1） | 2015 | UNLABELED | 足迹 ≈501 km²（11.6% ROI） | 0 | 0 | 本地 | 仅自监督预训练 |
| U6 浙江 11 波段特征堆叠 A/B | 2015 | UNLABELED | A 92.6% | A 100% | A 80.9% + B 19.1% | 本地 | 字节级审计待 M2.1b |
| U8 乐清湾 S2 合成体 2019–2025 | 2019–2025 | UNLABELED | 0 | 0 | 仅 24.52 km²（4.2% ROI） | 本地 | 同上 |

- **GOLD = 0；GOLD 候选 = 0**。所有行
  `gold_candidate_issue=ISSUE_11_OWNS_GOLD_PROMOTION;NO_GOLD_CANDIDATE_AT_M21A`，
  升级 GOLD 的权力保留给 Issue #11 流程；
- 可入训练分发的标签计数：**0**（SILVER 再分发受限；WEAK 仅诊断）；
  仅验证参考计数：L1 共 37.94 km²（两湾）；
- 所有 `verified_acquisition_date = UNKNOWN`（产品标称年 ≠ 实测
  成像日期）；
- 主要缺陷：来源/阈值未证实（L3）、浙江全省 39,764 个 L2 要素在
  三湾实测为 0（不得据此声称"无米草"）、CMSA 三年产品在湾头近
  重复、"Spartina"文件名不等于标签。

## 4. EO 观测普查（Q20–28）

方法：3 湾 × 42 年（1985–2026）× 6 传感器 = **756 组**；其中
294 组在轨期各发 1 次 `getInfo`（仅元数据 + 服务端足迹覆盖率），
462 组在传感器未服役期直接记 `SENSOR_NOT_OPERATIONAL`（零调用）。
原始 **18,435 景**全部留在 scene 表；全程无 `ee.batch.Export`
（运行期 guard + 单元测试 monkeypatch + 1 个真实凭证集成测试）。

### 4.1 各传感器有影像的年份跨度（观测事实，不是在轨声明）

| 传感器 | 在轨声明（config） | 三湾实际首景（UTC） | 实际末景 | 备注 |
|---|---|---|---|---|
| L5 LT05 C02 T1_L2 | 1984–2012 | 1985-01-11（HZB）；YQB 首景 1985-06-29 | 2011-11-12 | 2012 三湾均 0 景 |
| L7 LE07 C02 T1_L2 | 1999–2026 | 1999-08-06 | **2023-12-02/07** | 2024–2026 三湾均 0 景（2024-05 退役）；SLC 状态逐景标注，未删除 |
| L8 LC08 C02 T1_L2 | 2013–2026 | 2013-03-25 | 2026-09-18 | |
| L9 LC09 C02 T1_L2 | 2022–2026 | 2022-01-02 | 2026-09-26 | |
| S1 S1_GRD | 2014–2026 | **2015-02-09** | 2026-09-27 | 2014 三湾 0 景；升降轨分列；YQB 2023 仅观测到 ASCENDING |
| S2 S2_SR_HARMONIZED | 2017–2026 | 2017-01-26（HZB）/02-15（SMB、YQB） | 2026-10-01 | 记录 SPACECRAFT（2A/2B/**2C**）与 PROCESSING_BASELINE |

### 4.2 景数（湾 × 传感器）

| | L5 | L7 | L8 | L9 | S1 | S2 | 合计 |
|---|---|---|---|---|---|---|---|
| ZJ-HZB | 754 | 844 | 661 | 251 | 1,114 | 3,072 | 6,696 |
| ZJ-SMB | 665 | 653 | 422 | 146 | 764 | 1,220 | 3,870 |
| ZJ-YQB | 679 | 683 | 428 | 149 | 1,084 | 4,846 | 7,869 |
| 合计 | 2,098 | 2,180 | 1,511 | 546 | 2,962 | 9,138 | **18,435** |

### 4.3 通过预声明门槛（足迹覆盖 ≥0.99 且场景云量 ≤0.30；S1 只看覆盖）
的季节候选景数（autumn_v0 DOY260–305 / summer_v0 DOY152–212）

| | L5 | L7 | L8 | L9 | S1 | S2 |
|---|---|---|---|---|---|---|
| ZJ-HZB | 48 | 40 | 19 | 5 | 10 | **0** |
| ZJ-SMB | 48 | 41 | 18 | 8 | 118 | 37 |
| ZJ-YQB | **0** | 1 | 1 | 6 | 9 | **0** |

### 4.4 主要缺口（gap 分类，不插值）

- 462 组 `SENSOR_NOT_OPERATIONAL`（从未当作 0 景）；
- 15 个在轨组 `NO_SCENES_FOUND`：L5 2012、S1 2014、L7 2024–2026，
  各 3 湾；
- 83 个在轨组 `NO_QUALITY_SCENES`（L5 26、L7 23、L8 5、S1 9、S2 20）。
  关键实测事实：
  - **杭州湾 S2 单景最大足迹覆盖仅 0.909**（需 ≥3 个 MGRS 瓦片
    51RTP/RUP/RUQ 拼接），**乐清湾 S2 单景最大 0.98994**（51RUM），
    均差一点不达 0.99 → 单景门槛对瓦片式传感器过严，多瓦片合成是
    M2.1b 的正式入口，本阶段不调阈值、不洗白；
  - 乐清湾 L5/L7 窄湾 + WRS 帧几何下单景覆盖中位仅 ~0.80，
    1985–2011 基本无单景达标，但**影像本身大量存在**；
  - 三门湾各传感器覆盖最好（S1 单帧可全覆，季节候选 118 景）。
- 非 EO 轴：标签 121/126 个湾-年 `NO_LABEL`；field/UAV 全部
  `NONE_FOUND`；治理事件全部 `UNKNOWN`；潮位 126 个湾-年全部
  `MODEL_SELECTABLE_NOT_JOINED`。

## 5. 物候结论（Q29–32）

- 9 篇已核对文献（DOI 清单见物候文档，含 Zhou 2024、Ouyang 2013、
  张小伟 2026、Li 2020、Sun 2021、Xu 2025、Cao 2026 等）；
- 支持阶段：春末萌发 ~DOY121–130、秋季盛花 ~DOY265–275、
  秋末冬初枯黄滞后（晚本地种 1–2 个月）；
- 新证据（NASA POWER/CERES 2001–2020，2026-10-02 取数）：6 月云量
  全年最高 79–84%（梅雨），10 月最低 54–61%；仲夏生态窗口与云气候
  直接冲突；
- 旧窗口判定：`autumn_v0 260–305` → **MODIFY**（v1 候选 260–320）；
  `summer_v0 152–212` → **REGION_DEPENDENT**（真正物种分离在
  v1 候选 110–150；仲夏若用必须与秋末/冬初配对）。全部
  `PROPOSED_NOT_FROZEN`，需逐湾纬度标定。

## 6. 潮位结论（Q33–36）

- 候选：FES2022b（选定，未部署）、EOT20/GOT4.10c/HAMTIDE/
  TPXO10-atlas（集成，spread 作不确定性）、HYCOM/GLORYS12 增水；
- observed：公开逐时仅坎门（→1997-12-31）、吕泗（→1996-10-31）；
  NMDIS 注册墙 BLOCKED；基准面换算 BLOCKED；1992 前无增水再分析；
- 本项目全部用 observed_tide / modeled_tide / inundation_proxy /
  water_fraction_proxy 四类术语，UTC 匹配规则（30 min/3 h 阈值）
  已设计未执行；USGS DSWE 因 CONUS-only BLOCKED；
- 限制：模型未下载、未与任何景连接；不得用模型值冒充观测。

## 7. Holdout 与 GoldSet（Q37–41）

- 候选轨道（全为假设）：R1 HZB→SMB、R2 HZB→YQB、R3 留一湾轮换；
  T1 跨年代；S1 Landsat→Sentinel 代际；M1 缺模态；
- 泄漏控制：海岸分段 + 投影缓冲（候选 500 m，待变异函数证据）、
  同地跨日期同组、CMSA 三年产品必须同侧、L1/L3 同年同地禁跨训验；
  split 必须过 `splits.py` 检查；
- GOLD 潜在证据方向：野外调查/UAV/专家复核、乐清"一湾一策"
  （乐政办发〔2021〕20号，仅政策文本无空间台账）、Cao 2026 CC BY
  数据（比较对象，非自动 GOLD）；**M2.1a 不提升任何 GOLD，
  等 Issue #11**。

### 7.1 治理事件 schema 盘点（M2.1a：0 条记录）

提议 schema（未冻结）：`event_id, roi_id, segment_refs,
event_type(cutting/mowing, impoundment_flooding, plastic_mulch,
biological_replacement, dredging, seawall_works, other),
date_start, date_end, date_quality(OBSERVED/DECLARED/UNKNOWN),
area_km2_or_footprint, evidence_url, evidence_status, source_type,
notes`。盘点结果：**0 条可核验事件**；HZB/SMB 未找到空间化台账；
YQB 仅有政策文本提及整治。T1 治理前后切分因此暂缓。

## 8. Stage B 工作量评估与停止点（Q53）

- 按 §15/§39，Stage B（ROI_PIXEL_QA reduceRegion）只对季节候选
  景执行；当前预声明门槛下候选为 **409 景次**（HZB 122、SMB 270、
  YQB 17）；
- 但杭州湾/乐清湾 S2 候选为 0 是单景 0.99 门槛所致，Stage B 设计
  必须先就"多瓦片合成后 QA"做策略决定，否则 S2 代际在两个湾无
  样本——这是需要用户拍板的科学/工程决策；
- **M2.1a 在此 STOP：未运行任何 ROI 像素 QA，未创建任何 Export
  task，等待批准后才评估 Stage B EECU 与开 M2.1b。**

## 9. 指纹（Q42–45）

逐行逻辑指纹见三份 manifest 的 `*_fingerprint` 列；文件级
SHA-256（见 `zhejiang_m21a_artifact_fingerprints_v0.csv`）：

- ROI registry parquet：`913b2b2639942fa6…c4bffc2d25`
- 标签 inventory parquet：`f55e837a97da6866d…39d8ec`
- EO scene census parquet：`693b537c0c15e3ce…37ee95655`
- EO census summary parquet：`c682435ae113f0b3…fbc536ba31`
- availability csv：`e4c1ed28aa902d46…9db61b1c4`
- gap matrix csv：`7a62e1522b85c176…586e6d8`

## 10. 工程 QA（Q46–50）

- conda python3.11 `pytest tests/unit`：**216 passed**；
- 系统 `/usr/bin/python3`（3.10，无 ee）：**200 passed, 3 skipped**
  （跳过项均为既有可选依赖 fiona / segmentation_models_pytorch）；
- `pytest -m gee_integration`（新增 census 元数据测试）：
  **1 passed**（单组、单 getInfo、export guard 生效）；
- `ruff check .`：**All checks passed**；
- `mypy --strict src scripts`：**Success: no issues in 107 files**。

## 11. 未解决的科学/证据阻塞（Q54）

1. 无任何官方海湾矢量，三湾边界永久标记 PROVISIONAL_TIER_C；
2. 可训练标签 = 0、GOLD = 0、成像日期全部 UNKNOWN；
3. 单景 0.99 覆盖门槛与多瓦片传感器的矛盾（影响 S2/S1 全湾策略）；
4. 验潮逐时数据 1997 后在公开渠道 BLOCKED，潮位只能 modeled/proxy；
5. 治理事件空间台账为 0，T1 治理前后命题无法落地；
6. CMSA（L4–6）来源与许可证 UNKNOWN；L2 浙江要素在三湾为 0 的
   原因未解释（产品裁剪 vs 真实无分布）；
7. 物候窗口需逐湾实测标定，纬度梯度证据不足。

## 12. 判定（Q51–52）

- **M2.1a：PASS（待用户验收）**——§40 交付物齐备，所有数字来自
  实际执行，缺口与 BLOCKED 全部显式记录，无 Export、无训练、无
  冻结；
- 权威 ROI：**不存在**；三湾为已指纹化的 PROVISIONAL Tier-C；
- M2.1b：**未就绪且不得自动开始**——先决决策见 §8 与 §11。
