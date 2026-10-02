# 浙江三湾固定观测单元设计 v0（M2.1a2 / Issue #12）

- 阶段：M2.1a2 科学设计闸门（元数据 / 几何 / 策略 / 离线模拟，无像元生产）
- 状态：`RECOMMENDED_NOT_FROZEN`——10 km 为建议尺寸，冻结需用户验收
- 生成代码：[cells.py](file:///data/yingda/Spartina-Earth/src/spartina/data/zhejiang/cells.py)、
  [build_analysis_cells.py](file:///data/yingda/Spartina-Earth/scripts/data/zhejiang/build_analysis_cells.py)
- 产物：`datasets/manifests/zhejiang_analysis_cells_v0.{csv,parquet}`、
  `zhejiang_grid_specs_v0.csv`、`zhejiang_cell_grid_comparison_v0.csv`
- 配置：`configs/data/zhejiang_multibay_m21a.yaml::m21a2.grid`

## 1. 为什么需要新的观测单元

M2.1a 暴露三个结构性问题：

1. **湾多边形是区域身份，不是单景 QA 单元**。S2 单景对杭州湾覆盖最大
   0.909、乐清湾 0.98994，湾整体门槛（覆盖 ≥0.99）对瓦片式传感器系统性
   过严；2017–2026 杭州湾/乐清湾湾级 S2 秋季候选数为 **0**，但这不是
   "无数据"，而是 QA 空间单元错误。
2. **静态湾多边形不是历史岸线**。杭州湾存在大规模围垦，固定信封与日期
   相关海岸状态必须分离（§5）。
3. **采样框架不能由标签决定**。相关性过滤必须 target-independent，否则
   "无标签区"被系统性排除，早期复发检测无从谈起。

## 2. 三层空间语义（不可混用）

| 层 | 名称 | 状态 | 用途 | 禁止 |
|---|---|---|---|---|
| 1 | BayEnvelope 湾信封 | `PROVISIONAL_BAY_ENVELOPE_V0` | 区域身份、分组、汇总 | 当作单景 QA 单元；当作权威行政/岸线边界 |
| 2 | FixedAnalysisCells 固定分析格网 | `ZJ_U51_FIXED_V0` | 观测 QA、训练/评估空间单元、指纹锚点 | 随年份/传感器重划 |
| 3 | CoastalState 日期相关海岸状态 | schema 已立，M2.1a2 仅示例行 | 历史岸线/掩膜/潮间带接口 | 用静态信封冒充（见 [coastal.py](file:///data/yingda/Spartina-Earth/src/spartina/data/zhejiang/coastal.py)） |

## 3. 固定格网定义

- CRS：EPSG:32651（UTM 51N）；**全浙江一个锚点** (0, 0)；
- 索引：对锚点向下取整，`cell_id = ZJ_U51_51_{5K|10K|20K}_E{ix:03d}_N{iy:03d}`，
  可由 ID 无损重建四角坐标（`parse_cell_id`）；
- 尺寸候选 5 / 10 / 20 km，格网严格嵌套（同一锚点的整数细分）；
- 湾归属：与湾信封相交面积最大者（max-intersection，确定性平局规则）；
  cell 方形允许跨信封边界——这是特性（跨边界可审计），cell 级标签面积
  因此与信封内面积不同（§6.2）；
- 内部不重叠：以 DE-9IM `T********` 断言（`cells_are_interior_disjoint`）；
- 每个尺寸有 registry fingerprint（全部行的规范化哈希）。

### 3.1 三尺寸实测对比（来自已执行构建）

| 尺寸 | 杭州湾 总/海岸相关 | 三门湾 | 乐清湾 | 合计/海岸 | registry fp |
|---|---|---|---|---|---|
| 5 km | 231 / 201（5 内陆、25 开阔水面） | 98 / 95（3 内陆） | 39 / 39 | 368 / 335 | `af1231a4dff9` |
| **10 km（建议）** | 68 / 67（1 内陆） | 30 / 30 | 16 / 16 | **114 / 113** | `af16814e098f` |
| 20 km | 23 / 23 | 8 / 8 | 8 / 8 | 39 / 39 | `c740e93a5f46` |

### 3.2 为什么建议 10 km（依据均非模型性能）

1. **传感器几何**：10 km cell 几乎总能被单 MGRS 瓦片完整覆盖
   （实测多瓦片并集相对单瓦片的"全覆盖增量"仅 22 对，见获取策略文档§4）；
   20 km 起跨越瓦片边界，5 km 则把一次过境切成 4 个无信息增益的 QA 单元。
2. **斑块尺度**：10 km 下标签正 cell 数 53/114，正面积分布既有>7 km² 的
   连续斑块也有亚 km² 小斑块，粒度足以区分"核心分布 vs 边缘"。
3. **成本**：10 km 标准档全湾生物窗口质量事件约 64 GB（规划估算），
   5 km 同口径像素量约 4 倍；20 km 仅 39 个海岸 cell，跨湾异质性被平均掉。
4. **泄漏防护**：10 km 提供足够缓冲宽度，便于后续按 cell-group 做空间
   不相交划分（正式 split 在 M2.1b 之后，本阶段不冻结）。
5. **标签密度**：10 km 下 SILVER/SILVER+WEAK/WEAK/UNLABELED 四类同时
   存在且数量可用于分层；5 km 过度碎片化，20 km 单元内标签异质性不可见。

## 4. Target-independent 海岸相关性

- 方法：GSHHG v2.3.7 L1（mean shoreline，配置中钉死 sha256，LGPL-3.0）
  海陆界面两侧各 5 km 缓冲带；与缓冲带相交 → `COASTAL_RELEVANT`，
  其余按陆面占比 ≥0.5 标 `NOT_RELEVANT_INLAND`，否则
  `NOT_RELEVANT_OPEN_WATER`。
- 不使用任何标签/指数产品决定相关性。
- 335 / 113 / 39 个海岸相关 cell（5/10/20 km）进入模拟。

## 5. CoastalState（日期相关海岸状态）

固定 cell 是采样框架；历史岸线、围垦、潮滩边界属于 **CoastalState**：

- schema 见 [coastal.py](file:///data/yingda/Spartina-Earth/src/spartina/data/zhejiang/coastal.py)
  （cell_id、record_date、land/water_fraction、intertidal/inundation_proxy、
  shoreline_source/version、status、fingerprint）；
- 状态枚举：OBSERVED / MODELED / PROXY / MISSING / SIMULATED_NOT_DERIVED；
- M2.1a2 仅输出 schema 示例：
  `datasets/manifests/zhejiang_coastal_state_example_v0.csv`（每湾首个
  cell × 2000/2015/2025-09-15 三日期 `SIMULATED_NOT_DERIVED` + 一行
  2026-01-01 `MISSING`），**没有派生任何真实岸线产品**；
- 潮位接口保留 17 字段 `TIDE_CONTEXT_FIELDS`；FES2022b 维持
  SELECTED_NOT_DEPLOYED，实测潮位站覆盖止于 1990s；
  `tide_context_status=MISSING` 仅允许 M2.1b 管线验证，不允许最终冻结。

## 6. 标签 × cell 重叠（10 km，已执行）

产物：`zhejiang_label_cell_overlap_v0.csv`（5/10/20 km 全量）、
`zhejiang_hzb_label_disagreement_v0.csv`。

### 6.1 cell 级标签状态（UNLABELED ≠ NEGATIVE，永不输出 NEGATIVE）

| 湾 | SILVER | SILVER+WEAK | WEAK | UNLABELED |
|---|---|---|---|---|
| 杭州湾 | 14 | 4 | 1 | 49 |
| 三门湾 | 21 | 0 | 0 | 9 |
| 乐清湾 | 8 | 5 | 0 | 3 |

### 6.2 信封口径与 cell 方口径不同（重要审计发现）

M2.1a 标签清单按**湾信封内**统计：L1 在三门湾信封内为 0 km²。按
**10 km cell 方形**统计，三门湾归属 cell 内 L1 正面积 45.58 km²、
21 个 cell——这些标签落在 cell 方形伸出信封的部分（杭州湾侧/信封外）。
杭州湾 cell 内 19.97 km²（信封内 17.34）、乐清湾 27.33（信封内 20.60）。
两种口径都保留：信封口径回答"湾内有什么"，cell 口径回答"训练单元里
有什么"。不以任一口径改写另一个。

### 6.3 杭州湾 2015 SILVER(L1) vs WEAK(L3) 分歧层

两栅格 warp 到 cell 公共 30 m EPSG:32651 格网（最近邻，~1 px 容差，
仅诊断、不重新裁定）。4 个 cell 两产品同时为正：

| cell | 公共格网一致 px | Jaccard |
|---|---|---|
| ZJ_U51_10K_E031_N335 | 195 / 并集 4484 | **0.0435（近乎不重合）** |
| ZJ_U51_10K_E032_N336 | 927 / 1560 | 0.5942 |
| ZJ_U51_10K_E033_N336 | 6350 / 8676 | 0.7319 |
| ZJ_U51_10K_E034_N335 | 2380 / 3885 | 0.6126 |

另有 3 个 cell 仅单一产品为正。结论：两套 2015 产品存在真实空间分歧，
不能静默合并或互相覆盖。

### 6.4 GoldSet 目标（只立目标，不做晋升；晋升归 Issue #11）

19 个 10 km cell 标 `GOLD_EVIDENCE_TARGET`，理由四类：
HZB 同期 SILVER/WEAK 分歧、YQB 2015 SILVER vs 2019–2021 CMSA WEAK 时间
分歧、WEAK-only 证据升级、三门湾无标签 cell 的跨湾空白。
确定性预注册 3 个 `RESERVED_FOR_GOLDSET`（默认禁止训练）：

| cell | 湾 | 理由 |
|---|---|---|
| ZJ_U51_10K_E033_N336 | 杭州湾 | HZB 同期分歧，正面积最大 |
| ZJ_U51_10K_E032_N313 | 乐清湾 | CMSA 时间分歧，CMSA 面积最大 |
| ZJ_U51_10K_E034_N320 | 三门湾 | 跨湾标签空白，最低 ID |

## 7. 三级导出量规划估算（未执行任何导出）

`zhejiang_export_volume_estimate_v0.csv`。假设：cell=100 km²；Landsat
111,111 px/cell ×13 B；S2 1,000,000 px ×20 B；S1 1,000,000 px ×8 B
（规划字节假设，非实测；压缩后实际更小）。

| 档 | 定义 | cell×event 对 | 估算 |
|---|---|---|---|
| minimal | 三门湾、2023–2025、autumn_primary_v1、质量通过、名义几何 | 303 | **3.97 GB** |
| standard | 三湾 113 海岸 cell、全部年份、两个生物窗口、质量通过 | 13,023 | **63.5 GB** |
| full | 全部日期全部相交对（含被云拒绝光学） | 248,606 | **≈1.97 TB** |

生产档排除 L7 扩展科学任务（2022-04 降轨后，名义 WRS 几何失效）场景，
共 57 个 L7 事件（2022-05-21–2023-12-07）保留在 full 档并带
`L7_EXTENDED_SCIENCE_MISSION_LOWER_ORBIT_WRS_APPROXIMATION` 标记。

## 8. 明确不做（本阶段）

- 不冻结 10 km 尺寸、不冻结任何 split；
- 不导出像素、不批量 GEE、不生产湾级 GeoTIFF；
- 不把信封重标为权威边界、不派生真实岸线、不部署潮汐模型；
- 不把 UNLABELED 当负样本、不把任何标签晋升 GOLD；
- 不据模拟结果回头放宽 0.99 / 0.30 阈值（阈值未改，仅改 QA 空间单元）。
