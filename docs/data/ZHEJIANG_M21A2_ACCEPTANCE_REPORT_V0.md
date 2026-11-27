# 浙江多湾 M2.1a2 验收报告（Issue #12：观测单元 / 分组 / 标签闸门）

- 状态：**GATE PASS（科学设计闸门通过；受控像元生产尚未放行）**
- 分支：`reboot/spartina-earth-m0`（仅本地提交；未 push / merge / rebase）
- 日期：2026-07（执行日）
- 范围：仅元数据、几何、策略、离线模拟。**未执行**任何批量 GEE 导出、湾级 GeoTIFF 下载、跨十年像元生产、模型训练、split 冻结。
- 反编造口径：所有数字来自本阶段 manifest（指纹见 J 节与
  `datasets/manifests/zhejiang_m21a2_artifact_fingerprints_v0.csv`）；
  未观测项一律标 `UNKNOWN` / `MISSING` / `SIMULATED_NOT_DERIVED`。

---

## A. Grid

### 1. tested cell sizes
5 km、10 km、20 km 三种，全部落在同一固定格网 `ZJ_U51_FIXED_V0` 上，海岸带半宽 5,000 m。

### 2. cells per bay（总 cell 数）

| 尺寸 | HZB 杭州湾 | SMB 三门湾 | YQB 乐清湾 | 合计 |
|---|---:|---:|---:|---:|
| 5 km | 231 | 98 | 39 | 368 |
| 10 km | 68 | 30 | 16 | 114 |
| 20 km | 23 | 8 | 8 | 39 |

### 3. coastal cells per bay（海岸相关 cell）

| 尺寸 | HZB | SMB | YQB | 合计 |
|---|---:|---:|---:|---:|
| 5 km | 201 | 95 | 39 | 335 |
| 10 km | 67 | 30 | 16 | **113** |
| 20 km | 23 | 8 | 8 | 39 |

5 km 下另有内陆 8、开阔水体 25；10 km 仅 HZB 1 个内陆 cell；20 km 无剔除。

### 4. selected/recommended size
**10 km**：`recommended=True`，状态 **RECOMMENDED_NOT_FROZEN**（建议、未冻结，M2.1b 首批生产后可复核）。5 km 与 20 km 均为 `False / RECOMMENDED_NOT_FROZEN`。

### 5. justification
- 10 km 的 cell×event 规模适中：**248,606 相交对 / 56,096 质量对**；
  5 km 为 711,117 / 170,037（约 3 倍），20 km 为 95,157 / 18,582。
- 多瓦片并集的**纯增量**（单帧 <0.99 而并集 ≥0.99）：5 km **0**、
  10 km **22（全部位于 YQB）**、20 km **0**。S2 恢复的主因是 **QA 空间单元由湾门限改为 cell×event**，不是拼接本身。
- 20 km 对潮汐湿地过粗（单 cell 混入多类生境）；5 km 导出量与标签碎片化代价高。
- 10 km 与 30 m 标签公共格网配准良好（分歧诊断见 F 节）。
- 0.99 覆盖门限与 0.30 云门限**均未放宽**，只改了门限施加的空间单元。

### 6. grid origin
UTM 锚点 **anchor_easting=0, anchor_northing=0**（WGS84 UTM 51N 格网原点），非任意局部原点；cell ID 形如 `ZJ_U51_10K_E031_N335`（湾 + 尺寸 + 东向/北向索引）。

### 7. CRS
**EPSG:32651（WGS84 / UTM zone 51N）**，覆盖三湾。

### 8. registry fingerprint（registry_fingerprint，sha256，完整值见 grid spec）
- 5 km：`af1231a4dff9…cc0b2`
- 10 km：`af16814e098f…b03492`
- 20 km：`c740e93a5f46…f48433`

湾信封（ROI envelope）维持 **PROVISIONAL**，未因建网而升级。

---

## B. Multi-tile（S2 分组与恢复）

### 9. S2 grouping rule
按 **DATATAKE_IDENTIFIER + UTC 日期 + 传感器**聚合成一个 AcquisitionGroup；同一 datatake 的多 MGRS 瓦片（实测 1–8 瓦片：7 瓦片 558 组、8 瓦片 543 组）合并为一次事件。**禁止跨日期拼接**。

### 10. metadata fields used
`DATATAKE_IDENTIFIER`、`MGRS_TILE`、`SPACECRAFT_NAME`、`relativeOrbitNumber_start`、`system:time_start`。补充盘点共 **14,401 S2 景，datatake 缺失 0**。

### 11. fallback if DATATAKE missing
代码保留 fallback：datatake 缺失时退化为「同日 + 同航天器」键并打 `DATATAKE_IDENTIFIER_MISSING` 标记；本批数据**未触发**（1,345 个 S2 事件全部 `DATATAKE_IDENTIFIER_PRESENT`）。

### 12. no-cross-date proof
- 分组键含 UTC 日期，`_build_group` 仅在同传感器同日成员上构建；
- 5,244 个事件中 S2 1,345 个全部可由 datatake 归组，datatake 盘点 0 缺失；
- 单元测试覆盖「不同日期不得并组」断言（32 测试全过）；
- 策略文档明令禁跨日期合成。

### 13–15. 恢复的 cell×event 质量对（10 km；旧湾门限 → 新 cell×event）

| 窗口 | HZB | SMB | YQB |
|---|---:|---:|---:|
| autumn_v0 | 0 → **301** | 22 景 → **570** | 0 → **407** |
| autumn_primary_v1 | 0 → **444** | 26 景 → **780** | 0 → **512** |
| summer_v0 | 0 → **75** | 15 → **180** | 0 → **62** |
| early_season_v1 | 0 → **71** | 17 → **120** | 0 → **45** |

autumn_v0 按年（HZB/SMB/YQB）：2017 25/30/35，2018 9/0/27，2019 79/180/118，
2020 24/30/46，2021 87/180/106，**2022 0/0/0**，2023 47/90/45，
2024 15/30/15，2025 15/30/15，2026 0。

### 16. coverage distributions（10 km）
- **质量对**覆盖分数：六传感器中位数与 P90 均 = 1.0；近似全覆盖（≥0.999999）占比
  L5 0.970 / L7 0.969 / L8 0.965 / L9 0.960 / S1 1.000 / S2 0.982。
- S2 **全部相交对**覆盖分数：P10 0.977、中位 1.0，≥0.99 占 **87.3%**；
  低于 0.99 的多为单瓦片边缘 cell。
- 多瓦片并集纯增量仅 22 对（全在 YQB，10 km），印证恢复主要来自 QA 空间单元改变。
- `NO_QUALITY`（有数据但未过门限）**不等于无数据**。

---

## C. Landsat

### 17. cell coverage behavior
名义 WRS 帧幅远大于 cell，质量对覆盖中位/P90 = 1.0，约 96–97% 质量对为近似全覆盖（见 B16）。全期 10 km 质量对：

| 湾 | L5 | L7 | L8 | L9 |
|---|---:|---:|---:|---:|
| HZB | 9,999 | 10,073 | 5,108 | 1,821 |
| SMB | 4,029 | 3,636 | 1,936 | 758 |
| YQB | 1,579 | 1,535 | 704 | 240 |

事件构成（总/多帧）：L5 1,086/343，L7 1,082/361，L8 692/242，L9 247/90。

### 18. WRS boundary issues
- 使用名义 WRS 几何（`GEOM_NOMINAL_WRS`），相邻帧链并组处理跨轨边缘 cell；
  未见系统性 WRS 边界空洞，但**名义几何未用真实景足迹校正**。
- **Landsat-7 扩展科学任务**（2022-04-01 起，降轨后 8 km 条带，续取至 2024-01-19，
  USGS/EROS；2025-06-04 退役，访问日期 2026-10-02）单独标
  `GEOM_L7_EXTENDED`；配置项为
  `EXCLUDE_FROM_M21B_NOMINAL_PRODUCTION_PENDING_REVIEW`。
  生产候选窗口内涉 **57 个事件（2022-05-21 – 2023-12-07）**，标准档已排除。

## C2. Sentinel-1

### 19. asc/desc counts（10 km 质量对）
- HZB：升轨 **168** / 降轨 **868**
- SMB：升轨 **69** / 降轨 **210**
- YQB：升轨 **3,531** / 降轨 **7**

### 20. relative-orbit grouping
按相对轨道 + 升/降轨方向 + 日期归组；**帧几何为代表性近似
（`GEOM_S1_REPRESENTATIVE`）**，非逐景真实 footprint。YQB 几乎全由升轨覆盖，
HZB/SMB 以降轨为主——跨湾合并观测前必须保留轨道方向维度。

### 21. coverage behavior
S1 质量对覆盖中位/P90 = 1.0、近似全覆盖占比 1.000（基于代表性帧几何，属乐观上界；
真实景几何到位后必须重算）。全期质量对：HZB 1,036、SMB 279、YQB 3,538。

---

## D. Phenology（物候窗口）

### 22–24. 各湾候选窗口的 cell×event 质量对（10 km；见 B13 表）
四个候选窗口（autumn_v0 旧版、summer_v0 旧版、autumn_primary_v1 新版、
early_season_v1 新版）的每湾恢复量已在 B 节列出。关键观察：
- autumn_primary_v1 为三湾提供最大秋季覆盖（444/780/512）；
- 旧 autumn_v0 湾级门限在 HZB、YQB 给出 0，且 **2022 秋三湾全部 0 事件**；
- 月度云通过事件（HZB/SMB/YQB）：12 月 34/32/37、1 月 32/26/31、
  11 月 27/24/24；6 月 3/4/4、7 月 2/3/3——秋冬云窗可用性显著高于夏季。

### 25. biological vs availability evidence
文档（§7）将两层分离：
- **生物层**：物候/立地知识（先验，不做硬门限）；
- **可用层**：逐 cell×event 的实测 QA（云、覆盖）结果。
CERES 等物候证据降级为 **CONTEXT_ONLY_NOT_GATE**（仅供背景，不作准入闸口）。

### 26. status of old windows
旧窗口（autumn_v0 / summer_v0）保留作对照但不再作为生产定义；v1 窗口
（autumn_primary_v1 / early_season_v1）状态 **PROPOSED_NOT_FROZEN**。
门限值未放宽；变更仅为 QA 空间单元。

---

## E. Label rights（20 资产，完整矩阵见
`datasets/manifests/zhejiang_label_rights_v0.csv`）

### 27. each label source（分析 / 内部训练 / 验证 / 再分发 / 模型发布）

| 资产 | 层级 | 分析 | 训练 | 验证 | 再分发 | 模型发布 | 署名 |
|---|---|---|---|---|---|---|---|
| **L1** china2015-raster30m（geodata.cn） | SILVER | YES | **UNKNOWN** | YES | **NO** | **UNKNOWN** | YES |
| **U1–U5** HZB 2015 上游开放产品（5 行） | UNLABELED | YES | YES | YES | UNKNOWN | UNKNOWN | YES |
| **U8** YQB S2 合成 2019–2025（7 行） | UNLABELED | YES | YES | YES | UNKNOWN | UNKNOWN | YES |
| **L2–L6**（cmssm/cmsa/杭州 mask，5 行） | WEAK | UNKNOWN×5 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **U6–U7** feature stack A/B（2 行） | UNLABELED | UNKNOWN×5 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

状态枚举：L1 与 U1–U5/U8 共 13 行为 `AUDITED_TEXT_SUPPORTED`（有审计到的页面文本，
但 U* 的再分发/模型发布**本地许可链不可验证**）；L2–L6、U6、U7 共 7 行为
`NO_LICENSE_TEXT_LOCATED_ALL_UNKNOWN`。

### 28. unresolved permissions
- L1：内部训练权 UNKNOWN、再分发 NO、模型发布 UNKNOWN——**不能进训练集、不能随产品再分发**；
- U1–U5/U8：再分发与模型发布 UNKNOWN（开放页面 ≠ 可再分发授权，本地链缺证据）；
- L2–L6/U6/U7：五权全部 UNKNOWN，仅可作为 WEAK 诊断对象，不可训练、不可发布；
- 所有 UNKNOWN 不得在后续阶段静默升级为 YES。

---

## F. Label overlap（10 km，方形成像口径；湾信封口径另列）

### 29. SILVER-positive cells
HZB **14**（另有 SILVER+WEAK 4）、SMB **21**（0）、YQB **8**（另有 5）；
SILVER 并集 18 / 21 / 13。

### 30. WEAK-positive cells
WEAK-only：HZB 1、SMB 0、YQB 0；含 SILVER+WEAK 的 WEAK 并集为 5 / 0 / 5。

### 31. disagreement cells
共 **7 个分歧 cell**（HZB L1-SILVER vs L3-WEAK，公共 30 m 格网；本层**仅诊断、不重新裁定**）：
- 双正 cell 的 Jaccard：E031_N335 **0.0435**、E032_N336 **0.5942**、
  E033_N336 **0.7319**、E034_N335 **0.6126**；
- L1-only：E030_N336（261 px）、E034_N336（357 px）；
- WEAK-only：E032_N335（976 px）。

口径差异（方形 cell 内 vs 湾信封，SILVER km²）：SMB L1 **45.58 / 21 cell**
（湾信封口径为 0）、HZB 19.97（信封 17.34）、YQB 27.33（信封 20.60）。
信封 PROVISIONAL 是差异来源之一。

### 32. unlabeled cells
HZB **49**、SMB **9**、YQB **3**。`UNLABELED` 仅表示无标签，
**永不写成 NEGATIVE**。

---

## G. GoldSet

### 33. RESERVED_FOR_GOLDSET candidate regions
- **19 个 GOLD_EVIDENCE_TARGET**：
  HZB 5（E031_N335, E032_N335, E032_N336, E033_N336, E034_N335）；
  YQB 5（E031_N312, E031_N313, E032_N312, E032_N313, E032_N314）；
  SMB 9（E034_N320/N321/N323/N324、E035_N324、E036_N324、E037_N324、
  E038_N320、E039_N320）。
- **3 个 RESERVED_FOR_GOLDSET cell**（分歧重叠区，优先野外/UAV 取证）：
  E033_N336（HZB）、E032_N313（YQB）、E034_N320（SMB）。

### 34. no GOLD promotion
本阶段**零 GOLD 晋升**：无任何 SILVER/WEAK 被改级；目标 cell 只登记为待取证。

---

## H. Tide（潮位）

### 35. interface status
仅有 M2.1a 的策略文档（`ZHEJIANG_TIDE_INUNDATION_POLICY_V0.md`）；
`src/spartina/data/zhejiang/` 下**无潮位接口代码**，本阶段未建潮位服务。
CoastalState 仅有示例行，标记 **SIMULATED_NOT_DERIVED + MISSING**，
不来自任何潮位模型。

### 36. FES status
**FES2022b 未部署、未下载**（EOT20/GOT4.10c/HAMTIDE/TPXO10/HYCOM/GLORYS/GSW
同样均未下载）。

### 37. blockers
- 澉浦/镇海/温州公开档案**无逐时潮位序列（MISSING/BLOCKED）**；
- 无许可确认的潮汐模型本地部署；
- 在潮位状态派生前，潮间带 cell 的「出露/淹没」不可作为像元生产的质量门限。

---

## I. Production estimate（13 波段/Landsat px、20 波段/S2、8 波段/S1；cell=100 km²）

### 38. Landsat export count（cell×event 对）
- minimal：L8 **28** + L9 **65** = **93**
- standard：L5 4,107 + L7 3,996 + L8 1,316 + L9 392 = **9,811**
- full：53,639 + 55,258 + 34,325 + 12,794 = **156,016**（已排除 L7 扩展任务 57 事件）

### 39. Sentinel-2
minimal **180**；standard **1,972**；full **84,069**。

### 40. Sentinel-1
minimal **30**；standard **1,240**；full **8,521**。

### 41. estimated storage
- minimal：**303 对 / 3.97 GB**
- standard（质量 × 生物窗口）：**13,023 对 / 63.53 GB**
- full（全部候选日期）：**248,606 对 / ≈1,974.91 GB**

估算为清单级，不含重投影/重复保留冗余；真正 Export 前需以 dry-run 复核。

---

## J. Reproducibility

### 42. grid fingerprint
见 A8（5/10/20 km registry fingerprint；grid spec fingerprint 另列于
`zhejiang_grid_specs_v0.csv`）。

### 43. acquisition simulation fingerprint
- 事件表（Git 内规范产物）
  `zhejiang_acquisition_group_simulation_v0.parquet`：
  sha256 `5193e744c0a8…b27271`（845,462 B）；
  宽表 CSV（2.25 MiB）依大文件政策只存 `work/derived/`
  （sha256 前缀 `4e795152dbaf0e76`）。
- 1,054,880 对长表 `work/derived/zhejiang_cell_observations_v0.parquet`
  不入库（sha256 前缀 `36bfd9c72c13c7a0`）。

### 44. rights fingerprint
`zhejiang_label_rights_v0.fingerprint.json`：20 资产，
registry fingerprint `4b5d46b1a4e2…ae4e9e2`。

### 45. label-cell fingerprint
`zhejiang_label_cell_overlap_v0.csv`：sha256 `2e204cc1f9ae…7cbd40`
（283,608 B）。

全部 17 个入库新产物（均 <1 MiB）的字节数与 sha256 登记于
`zhejiang_m21a2_artifact_fingerprints_v0.csv`。

---

## K. Engineering

### 46. pytest
- conda `spartina-earth`（Python 3.11）：`tests/unit` **248 passed**
  （含新增 32 个 M2.1a2 单元测试）。
- 系统 `/usr/bin/python3`（3.10）：基线 191 passed + 1 collection error
  （`census.py` 使用 `datetime.UTC`，M2.1a 既有）；本阶段新增测试经
  `acquisition → census` 导入链使 collection error 增为 2，属同一既有限制，
  非新缺陷。

### 47. gee integration
`-m gee_integration` 新增 M2.1a2 集成测试 **1 passed**（实测 1 次 getInfo，
验证 `DATATAKE_IDENTIFIER` 元数据可用；`install_export_guard(ee)` 拦截
`ee.batch.Export.*`，任何导出尝试抛 `ExportAttempted`）。未触发任何 Export。

### 48. ruff
`ruff check .`：**All checks passed**。

### 49. mypy
`mypy --strict src scripts`：**Success: no issues found in 118 source files**。

### 50. commits
本阶段 4 个本地提交（无 push）：
1. `feat(m2.1): define Zhejiang fixed analysis cells`
2. `feat(m2.1): implement multi-tile acquisition groups`
3. `feat(m2.1): separate label-use and redistribution rights; map labels to cells`
4. `feat(m2.1): record observation-unit design gate（docs/config/fingerprints/本报告）`

---

## L. Decision

### 51. M2.1a2 PASS / FAIL
**PASS**（作为受控像元生产前的科学设计闸门）。全部结论可追溯至带指纹的 manifest；
无导出、无训练、无 split 冻结、无 GOLD 晋升、无指标编造。

### 52. is M2.1b controlled pixel production ready?
**尚未完全就绪（NOT YET — 限定条件下放行最小子集）**。设计、分组、QA 空间单元、
权利矩阵与导出预算已就绪；但有 6 项闸门须在扩大生产前关闭（见 54）。

### 53. what exact subset should be produced first?
建议首个极小生产子集（**minimal，303 对 / ≈3.97 GB**）：
- 格网：**10 km 固定格网（RECOMMENDED_NOT_FROZEN）**；
- 湾：**YQB 乐清湾**（S1 覆盖最稳、S2 秋季可用、标签分歧最少）；
- 年份：**2023–2025**；
- 窗口：**autumn_primary_v1（PROPOSED_NOT_FROZEN）**；
- 几何：名义几何（Landsat `GEOM_NOMINAL_WRS`、S2 真实瓦片、
  S1 `GEOM_S1_REPRESENTATIVE`）；
- 内容：L8 28 + L9 65 + S2 180 + S1 30 = 303 对；
- 排除：L7 扩展任务事件；标签仅用权利允许项（YQB SILVER L1 可分析/验证，
  训练权 UNKNOWN → 不进训练）。
该子集必须先 dry-run 复核字节数，并作为后续标准档的校准锚点。

### 54. unresolved scientific blockers
1. **L7 扩展科学任务（2022-04 起，57 事件）**是否以降级几何进入任何产品——
   待人工评审，当前排除；
2. **潮位 MISSING**：FES2022b 未部署、验潮站逐时序列无公开档案，
   CoastalState 仅 SIMULATED_NOT_DERIVED；
3. **L1 训练权 UNKNOWN / 再分发 NO**；U1–U5/U8 再分发与模型发布链不可验证；
4. **L2–L6、U6、U7 五权全 UNKNOWN**——7 个资产不可训练/发布；
5. **2022 秋三湾 S2 零质量事件**——是观测实况还是目录缺口需独立核查
   （本阶段不作插补）；
6. **S1 代表性帧几何**是乐观上界，真实景足迹到位前覆盖统计须重算；
7. 湾信封仍 PROVISIONAL、v1 窗口 PROPOSED_NOT_FROZEN、10 km 格网
   RECOMMENDED_NOT_FROZEN——三者均待最小子集复核后才能冻结。

**本报告完成即 STOP；不开始 M2.1b，等待用户验收。**
