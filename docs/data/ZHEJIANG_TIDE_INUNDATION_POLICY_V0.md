# 浙江三湾潮位与淹没数据策略 v0（SOURCE SELECTION ONLY）

- 阶段：M2.1a 仅做**数据源选型与连接（join）规则设计**；未下载任何
  潮位产品，未对任何景做潮位连接。
- 状态：SELECTED_NOT_DEPLOYED / BLOCKED 项均如实标注。
- 证据访问日期：2026-10-01。

## 1. 术语（禁用泛化的 "tide"）

本项目所有清单与后续 join 只允许使用四类互斥标签：

| 标签 | 含义 | 允许的来源 |
|---|---|---|
| `observed_tide` | 验潮站逐时实测水位 | 公开验潮站档案（见 §2） |
| `modeled_tide` | 纯天文潮汐模型水位 | FES2022b / EOT20 / GOT4.10c / HAMTIDE / TPXO10 |
| `inundation_proxy` | 淹没范围的间接指示 | S1 GRD 水体、自算 Landsat DSWE、JRC GSW 历史掩膜 |
| `water_fraction_proxy` | 像元水体比例的间接指示 | 同上映射为连续比例 |

混合项允许组合标注，如 `MODEL+SURGE`；任何没有出处的水位值禁止写成
observed。

## 2. 实测水位：公开档案核查结果（BLOCKED 为主）

| 站 | 位置 | 公开逐时数据覆盖 | 结论 |
|---|---|---|---|
| Kanmen 坎门 | 28.0833N,121.2833E（UHSLC） | 1975 → **1997-12-31** | 仅早期可作 observed |
| Lusi 吕泗 | 江苏沿岸（UHSLC） | → **1996-10-31** | 仅早期可作 observed |
| Ganpu 澉浦 / Zhenhai 镇海 / Wenzhou 温州 | 杭州湾、浙中南 | 公开档案中**无**逐时序列 | MISSING |
| NMDIS（`mds.nmdis.org.cn` / `global-tide.nmdis.org.cn`） | 国家海洋信息中心 | 需中国身份证/机构注册 | **BLOCKED（注册墙）** |

- PSMSL 只有月均/年均订正水位（research quality），不足以做逐景匹配；
- 基准面换算（当地警戒潮位/理论深度基准面 ↔ 平均海平面）依赖未公开
  站档，**BLOCKED**；
- 因此对 1985–2026 的影像时间轴，`observed_tide` 实际只在
  ≤1997（坎门）/≤1996（吕泗）成立，且两站离三湾都有距离——杭州湾
  湾顶、三门湾、乐清湾在卫星时代基本没有公开逐时实测可连接。
  这一缺口按 `MISSING/BLOCKED` 记录，不用模型值冒充观测。

## 3. 选定的模型策略（尚未部署）

### 3.1 主模型：FES2022b

- 1/30° 全球潮汐模型，34 个分潮，含浅水非线性分潮 M4/M6/M8/S4/MS4，
  对杭州湾这类强潮、浅水、涌潮影响海湾尤其重要；
- AVISO 分发，注册后可用，许可为类似 CC-BY 的署名许可（**部署前
  TODO_VERIFY：在本仓库记录确切许可文本与版本号**）；
- M2.1a 未下载、未运行。

### 3.2 不确定性：模型集成（多模型一致性方法）

单模型水位在杭州湾顶误差可达分米级，必须以**模型间 spread 作为
不确定性**，而不是给单一真值：

| 模型 | 分辨率 | 备注/标识 |
|---|---|---|
| EOT20 | 1/8° | DOI [10.17882/79489](https://doi.org/10.17882/79489) |
| GOT4.10c | 0.5° | GSFC |
| HAMTIDE | 0.125° | U Hamburg |
| TPXO10-atlas | ~1/30° | OSU（许可需单独确认 TODO_VERIFY） |

输出要求（M2.1b 设计，不在本阶段实现）：每景给
`[median, spread, constituent_set, model_versions]`，spread 超阈值
的景只入诊断集。

### 3.3 风暴增水

- HYCOM GOFS3.0：1992-10 起；GOFS3.1：2014-07 → 2024-09；
  GLORYS12 日值：1993 起；
- 1992 年以前**没有**再分析增水产品，该时段标记
  `MODEL_ASTRONOMIC_ONLY_PRE_1992`，风暴导致的水位偏差不可见；
- 增水标记阈值（假设，待用站档校核）：|surge|>0.5 m 标记
  `SURGE_WARNING`，>1 m 标记 `STORM_EXCLUDE`。

## 4. 影像—水位时间匹配规则（设计，未执行）

- 影像时间一律换算为 **UTC**，取景中心时刻；census 全部
  `acquisition_utc` 已为 tz-aware UTC（有测试锁定，拒绝 naive 时间）；
- 与逐时观测匹配：|Δt| ≤ 30 min → `OBS`；
- 30 min < |Δt| ≤ 3 h 且两侧有实测 → 线性插值 → `OBS-INTERP`；
- 其余 → 潮汐模型 → `MODEL`；叠加增水再分析 → `MODEL+SURGE`；
- 落在资料缺口且模型分潮覆盖不足 → `EXCLUDE`，不猜测。

## 5. 淹没/水体指示产品选型（尚未部署）

| 产品 | 时空范围 | 本项目用途 | 状态 |
|---|---|---|---|
| USGS DSWE | CONUS only | 不可用（中国不在覆盖） | **BLOCKED** |
| Landsat C2 自算 DSWE | 1984 起（受 L5/L7 波段限制） | 光学 `inundation_proxy` | `PROVISIONAL`，需本仓库实现与验证 |
| S1 GRD 逐景水体 | 2014-10 起 | SAR `water_fraction_proxy`，升降轨分列 | 可选，需潮位联合标定 |
| JRC Global Surface Water | 月历 v1.4 + v1.5 拼接，1984–2024 | 长期水体频率先验，不做逐景潮位 | 可引入，注意版本拼接边界 |

自算 DSWE 与 S1 水体都不是"潮位观测"，只能进入 `*_proxy` 标签；
GSW 月历是气候态，禁止与单景水位混用。

## 6. 与三湾已知潮差事实的关系（仅背景，不用于标签）

三门县政府自然地理页（2026-04-13 更新，原文核对）记载三门湾
平均潮差约 4.25 m、最大约 7.75 m
（https://www.sanmen.gov.cn/art/2025/6/26/art_1229679902_59040617.html）。
该数值说明三门湾为强潮海湾、淹没范围对潮时极敏感，因此
"无潮位不采潮滩像元"是硬约束；但网页数字不替代验潮数据。

## 7. M2.1a 的实际产出与边界

- 产出：本选型文档 + 术语表 + join 规则 + 缺口登记；
- census 层面已把"潮位元数据状态"写入
  `zhejiang_data_gap_matrix_v0.csv`（`tide` 轴，全部
  1985–2026×3 湾行）：`MODEL_SELECTABLE_NOT_JOINED` 与
  `PUBLIC_GAUGE_OBS_BLOCKED_POST_1997`；
- 明确未做：未下载 FES/EOT/GOT/HAM/TPXO/HYCOM/GLORYS/GSW；
  未对 18,435 景中的任何一景做潮位连接；未训练任何淹没分类器。
