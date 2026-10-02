# 浙江三湾获取事件（AcquisitionGroup）策略 v0（M2.1a2 / Issue #12）

- 代码：[acquisition.py](file:///data/yingda/Spartina-Earth/src/spartina/data/zhejiang/acquisition.py)
- 模拟：[simulate_acquisition_groups.py](file:///data/yingda/Spartina-Earth/scripts/data/zhejiang/simulate_acquisition_groups.py)
- 产物：`zhejiang_acquisition_group_simulation_v0.parquet`（5,244 事件，Git 内规范产物；宽表 CSV 超 1 MiB 仅存 `work/derived/`）、
  `work/derived/zhejiang_cell_observations_v0.parquet`（1,054,880 对）、
  `zhejiang_cell_observation_stats_v0.csv`、`zhejiang_s2_recovery_v0.csv`、
  `zhejiang_monthly_availability_v0.csv`
- 全部为离线几何 + 场景元数据模拟；无像素、无 GEE 导出。

## 1. 核心定义

**AcquisitionGroup（观测事件）**：同一 UTC 日期、同一传感器、同一物理
过境中覆盖区域的景集合。每个事件有 `group_id = AG_<sha256[:16]>`，
指纹载荷含传感器、UTC 起始时刻、航天器、轨道方向、相对轨道、模式、
极化、排序后成员景 ID 与帧键。**跨日期拼接在结构上不可能**：日期在
每个传感器的分桶键里，`_build_group` 对成员日期集合做断言。

## 2. 各传感器分组规则（已对真实 census 执行）

| 传感器 | 同事件条件 | 主键 |
|---|---|---|
| Sentinel-2 | 同一真实 `DATATAKE_IDENTIFIER`（同一次 datatake 跨 MGRS 瓦片）；属性缺失时退化为 航天器+UTC 日期+相对轨道 并标记 `FALLBACK_SAME_DATE_REL_ORBIT` | datatake |
| Landsat 5/7/8/9 | 同传感器同 UTC 日期，WRS path/row 曼哈顿相邻（\|Δp\|+\|Δr\|=1）的**连通链**（并查集）；不连通的同日帧拆成不同事件 | WRS 连通链 |
| Sentinel-1 | 日期+航天器+升降轨+相对轨道+模式+极化全等 | 复合键 |

- Landsat 用连通链而非团（clique）：真实观测到同日 118/039+118/040+
  118/041 三行链（039 与 041 距离 2，团约束会错误拒绝）。
- S1 升/降轨混合在结构上不可能（键含 orbit_direction）。
- S2 多瓦片事件的云门槛起伏保守：**任一成员景云量 >0.30 则整事件
  对该 cell 判 FAIL_SCENE_CLOUD**（成员云量最大值）。

### 2.1 真实 datatake 证据（live GEE，2026-10-02）

- 帧注册抽样：8/8 个 S2 代表帧存在 `DATATAKE_IDENTIFIER` 属性；
- 年度区域补充：2017–2026 共 **14,401 个 S2 景，datatake 缺失 0**
  （10 次年区域 getInfo，无导出）；
- census 9,138 个 S2 景全部带真实 datatake（join 后），模拟中
  `DATATAKE_IDENTIFIER_PRESENT` = 1,345/1,345，fallback 零次；
- 真实跨瓦片同 datatake 实例：
  `GS2A_20170228T023631_008809_N05.00`（RTP+RUL）、
  `GS2A_20170126T023851_008337_N05.00`（RUP+RUQ）、
  `..._008623_...`（RTM+RUM+RUN）。

### 2.2 事件规模

18,435 census 行去重为 **16,681 个物理景**（1,754 行为跨湾信封重复）；
分为 **5,244 个事件，3,065 个多景事件**。

| 传感器 | 事件数（多景） | 帧几何体制 |
|---|---|---|
| L5 | 1,086（343） | NOMINAL_WRS_FRAME |
| L7 | 1,082（361，其中 57 扩展任务） | NOMINAL / L7_EXTENDED… |
| L8 | 692（242） | NOMINAL_WRS_FRAME |
| L9 | 247（90） | NOMINAL_WRS_FRAME |
| S1 | 792（747） | REPRESENTATIVE_FRAME_PER_TRACK_VARIES |
| S2 | 1,345（1,282） | NOMINAL_MGRS_TILE |

S2 事件瓦片数分布：1 瓦片 63、2:42、3:38、4:31、5:33、6:37、
7:558、8:543（浙江断面常被同一 datatake 7–8 个瓦片一次扫过）。

## 3. cell × 事件 QA（阈值未放宽，仅改空间单元）

- 覆盖：事件帧并集对固定 cell 的相交面积比，门限 **≥0.99（不变）**；
- 云：成员景最大云量 **≤0.30（不变）**；S1 不适用；
- 像元级 SCL QA 策略版本 `s2_scl_qa_v1_1` 保留到 M2.1b，
  `qa_basis=CELLxEVENT_GEOMETRY_COVERAGE_PLUS_MEMBER_SCENE_CLOUD_METADATA;
  PIXEL_SCL_QA_DEFERRED_TO_M21B`。
- 5/10/20 km 相交对 711,117 / 248,606 / 95,157；质量对
  170,037 / 56,096 / 18,582。

10 km 全期质量 cell×event 对：

| 传感器 | HZB | SMB | YQB |
|---|---|---|---|
| L5 | 9,999 | 4,029 | 1,579 |
| L7 | 10,073 | 3,636 | 1,535 |
| L8 | 5,108 | 1,936 | 704 |
| L9 | 1,821 | 758 | 240 |
| S1 | 1,036 | 279 | 3,538 |
| S2 | 2,664 | 4,740 | 2,421 |

S1 升降轨（10 km 质量对）：HZB 升 168/降 868；SMB 69/210；
YQB 升 3,531/降 7——三湾主导轨道方向相反，两方向必须独立保留。

## 4. S2 恢复结果（§19 核心问题：旧湾门限 0 候选是否等于无数据）

**不等于。** 旧湾级门限下杭州湾、乐清湾 2017–2026 全部窗口 S2 候选
为 0；改为 cell×事件 QA 后（10 km）：

| 窗口 | HZB 旧→新质量对 | SMB | YQB |
|---|---|---|---|
| autumn_v0 (260–305) | 0 → **301** | 22 景 → 570 | 0 → **407** |
| autumn_primary_v1 (260–320) | 0 → **444** | 26 景 → 780 | 0 → **512** |
| summer_v0 (152–212) | 0 → 75 | 15 景 → 180 | 0 → 62 |
| early_season_v1 (110–150) | 0 → 71 | 17 景 → 120 | 0 → 45 |

autumn_v0 按年（HZB/SMB/YQB 质量对）：2017 25/30/35，2018 9/0/27，
2019 79/180/118，2020 24/30/46，2021 87/180/106，**2022 0/0/0**，
2023 47/90/45，2024 15/30/15，2025 15/30/15，2026 0/0/0（年未完整）。
2022 年秋季零质量事件为实测结果（云+调度），不修补、不标记为无数据。

**恢复几乎全部来自 QA 空间单元改变，而非多瓦片拼接**：S2 全覆盖对中
"单帧 <0.99 但多帧并集 ≥0.99"的纯增量在 5/10/20 km 分别为
0 / 22 / 0。多瓦片分组的价值在于来源可追溯与边缘/未来更大单元的
正确性，不是当前恢复的主因——如实记录，不夸大。

## 5. 真实月度可用性（10 km，2017–2026 合计，云/SAR 通过事件）

S2 每湾每月通过事件合计：12 月 34/32/37、1 月 32/26/31、
11 月 27/24/24；6 月 3/4/4、7 月 2/3/3（HZB/SMB/YQB）。
清晰季 **11–3 月**，低谷 **6–7 月**。L8 呈同形态；S1 三门湾/杭州湾
月样本稀疏、乐清湾充足（58–74/月，升轨）。该实测证据驱动配置中的
`sensor_availability_windows_m21a2`（11–3 月清晰、121–212 受限），
与生物目标窗口分层；CERES 云气候态降为 CONTEXT_ONLY_NOT_GATE。

## 6. Landsat 7 扩展科学任务（几何陷阱，已标记）

USGS 记录：2022 年 4 月降轨燃烧（约 8 km）后，L7 继续获取名义科学
影像至 **2024-01-19**，2025-06-04 退役。2022-04 起场景不再遵循名义
WRS 地面轨迹，名义 WRS 帧多边形仅为近似。模拟中 57 个 L7 事件
（2022-05-21–2023-12-07）带
`L7_EXTENDED_SCIENCE_MISSION_LOWER_ORBIT_WRS_APPROXIMATION`；
minimal/standard 生产估算排除这些场景，full 档保留。所有 2003-05-30
后 L7 事件另有 `slc_statuses=POST_SLC_FAILURE`（SLC-off）。
来源：USGS EROS Landsat 7 C2 L1 页面，2026-10-02 获取。

## 7. 帧注册表的近似性质

- S2：真实 MGRS 瓦片几何（8 个瓦片）；
- Landsat：真实 WRS 帧几何（9 个 path/row）；
- S1：5 个 pass/relorbit 键对应**代表性帧几何**（同一相对轨道沿轨
  实际足迹逐轨变化），任何覆盖结论带 PROVISIONAL 性质；
- 全部 21 个唯一键、每个特征带检索时间戳；
  `zhejiang_eo_frame_footprints_v0.geojson`。

## 8. 明确不做

- 不做跨日期/跨 datatake 拼接，不把 fallback 当真实 datatake；
- 不放宽 0.99/0.30，不把 NO_QUALITY 改写成"无数据"；
- 不用场景级云量替代像元 SCL QA（M2.1b 才做）；
- 不在 M2.1a2 冻结 split、不导出像素、不排除 SLC-off/扩展任务数据
  出档（只标记，生产档策略单列且待验收）。
