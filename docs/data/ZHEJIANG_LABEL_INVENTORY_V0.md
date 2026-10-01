# 浙江三湾 Legacy 标签资产盘点 v0（M2.1a / Issue #7）

- 产物：[datasets/manifests/zhejiang_legacy_label_inventory_v0.csv](../../datasets/manifests/zhejiang_legacy_label_inventory_v0.csv) / `.parquet`
- 代码：[scripts/data/zhejiang/build_label_inventory.py](../../scripts/data/zhejiang/build_label_inventory.py)
- 输入：`old datasets/`（永久只读、Git 忽略）；ROI 来自
  [datasets/rois/zhejiang_bays_v0.geojson](../../datasets/rois/zhejiang_bays_v0.geojson)
- 口径：矢量=真实相交要素数与相交面积（EPSG:32651）；栅格标签=窗口读取+ROI
  栅格化掩膜后的正像元数（>0 且非 nodata）；影像/特征堆栈=足迹相交，UNLABELED。
  全部数字为本次实算，未命中即 0，读不到即 MISSING_FILE，不用旧记录代替。

## 1. 汇总结论

- **GOLD：0。** 全部本地资产中没有任何 field/UAV/专家核验标签；也未发现可登记为
  GoldSet 候选的证据。任何 GOLD 立项与晋升归 Issue #11（GoldSet 协议），本阶段不产生。
- **SILVER：1 个**（L1 全国 2015），湾内实算正像元：杭州湾 19,268（17.34 km²）、
  乐清湾 22,889（20.60 km²）、三门湾 **0**。
- **WEAK：4 个**（L2 全国 2020 多边形、L3 杭州局地掩膜、L4–L6 局地多边形）。
- **UNLABELED：15 个**（杭州湾 2015 光学/SAR/指数 5 个、浙江 11 波段特征堆栈 2 个、
  2019–2025 局地 S2 合成 7 个，另含 1 个合成年度口径共 14 个影像行，合计见 CSV 20 行）。

## 2. 标签资产逐项结果

| asset_id | tier | 年 | HZB | SMB | YQB | 单位 | 湾内面积 km² | 再分发 |
|---|---|---|---:|---:|---:|---|---:|---|
| L1-china2015-raster30m | SILVER | 2015 | 19,268 | 0 | 22,889 | 正像元 | 37.94 | 受限 |
| L2-cmssm2020-polygons | WEAK | 2020 | 0 | 0 | 0 | 要素 | 0 | UNKNOWN |
| L3-hangzhou-mask-2015 | WEAK | ~2015 | 15,600 | 0 | 0 | 正像元 | 14.00 | UNKNOWN |
| L4-cmsa-polygons-2019 | WEAK | 2019 | 0 | 0 | 51 | 要素 | 8.82 | UNKNOWN |
| L5-cmsa-polygons-2020 | WEAK | 2020 | 0 | 0 | 158 | 要素 | 4.36 | UNKNOWN |
| L6-cmsa-polygons-2021 | WEAK | 2021 | 0 | 0 | 79 | 要素 | 9.11 | UNKNOWN |

观测像元值：L1 窗口内仅 `{1}`；L3 为 `{0,1}`。

### 相对 M0/M1.1 旧审计的两处实测修正

1. **L4–L6 “CMSA 福建多边形”实际位于浙江乐清湾湾顶片区**（bbox 实测
   约 121.150–121.220°E, 28.269–28.379°N，EPSG:4326），与福建无关；三年分别与
   ZJ-YQB ROI 真实相交 51/158/79 个要素。旧文档“疑似福建、NOT_APPLICABLE”的判断
   予以更正：它们是**乐清湾 WEAK 标签**（出处/方法仍 UNKNOWN，allowed_use 不变，
   仍为 DIAGNOSTIC_ONLY）。2020 年相交面积（4.36 km²）低于 2019/2021（8.82/9.11），
   与该年要素更破碎一致，记录现象、不做生态学推断。
2. **L2 CM-SSM 2020 在三湾 ROI 内命中 0 要素**，尽管 M0 审计记载“浙江省 39,764 个”。
   即该全国 WEAK 产品的浙江要素分布在三湾之外（省内其他岸段），三湾无 L2 覆盖；
   省级计数不能外推到湾。产品 2,402 自相交、10 万+ 碎面等缺陷维持原审计结论。

### L1 三门湾为 0 的解读

SILVER 全国产品在三门湾 ROI 内无正像元，可能反映 2015 年该湾确无/极少被识别分布、
或产品漏分；本阶段不判读、不补点，作为该湾**无 SILVER 标签覆盖**的事实缺口进入
gap matrix（BLOCKED 证据问题，不能以 WEAK 冒充）。

## 3. UNLABELED 影像/堆栈覆盖（足迹，不含标签语义）

- U1–U5 杭州湾 2015（L8 7 波段、NDVI、SAI、S1 VV/VH）：足迹与 ZJ-HZB ROI 相交
  约 501 km²（覆盖该湾 ROI 的 11.6%，南岸局地窗口，与 M1.4 pilot0 研究区一致），
  与 SMB/YQB 无交。
- U6 浙江 11 波段特征堆栈 tile-A（668 MB，28.03–30.72°N）：覆盖 HZB ROI 92.6%、
  SMB 100%、YQB 80.9%；tile-B（27.46–28.03°N）补 YQB 南口水域 19.1%。
  两 tile 合计对 SMB 全覆、HZB 近全覆、YQB 约全覆盖。**文件名含 “Spartina” 不构成
  标签证据**：其 11 个波段的特征构造与是否含标签层均 UNKNOWN，仅登记为
  UNLABELED/DESCRIPTIVE_ONLY，M2.1b 前必须做字节级内容审计。
- U8 2019–2025 局地 S2 合成（约 10 m，5 波段）：仅与 YQB 相交，足迹 24.52 km²
  （ROI 4.2%），逐年一片；无标签，云过滤/日期 UNKNOWN。

## 4. 许可与允许用途

| 资产 | 许可状态 | redistributable | allowed_use |
|---|---|---|---|
| L1 | geodata.cn 受限分发（产品页 OA≈92%） | NO_WITHOUT_PERMISSION | VALIDATION_REFERENCE |
| L2 | UNKNOWN + 几何缺陷 | UNKNOWN | DIAGNOSTIC_ONLY |
| L3 | UNKNOWN + 来源未解析 | UNKNOWN | DIAGNOSTIC_ONLY |
| L4–L6 | UNKNOWN | UNKNOWN | DIAGNOSTIC_ONLY |
| U1–U8 | 多为 UNKNOWN（上游 USGS/Copernicus 衍生） | UNKNOWN | DESCRIPTIVE_ONLY |

所有行均写 `gold_candidate_issue=ISSUE_11_OWNS_GOLD_PROMOTION;NO_GOLD_CANDIDATE_AT_M21A`。
verified_acquisition_date 全部 UNKNOWN（年份仅为名义年）；逐行含逻辑指纹（SHA-256）。

## 5. 明确缺口

1. 三门湾：无任何湾内标签（SILVER 0、WEAK 0）。
2. 乐清湾：无 SILVER；仅有来源不明的 WEAK 多边形 3 年。
3. 杭州湾：SILVER 17.34 km² + WEAK 局地掩膜 14.00 km²（M0 Jaccard 0.497，两者
   一致性低，不能互证）。
4. 全部资产缺乏可验证获取日期、现场证据与再分发许可；没有任何东西可在 M2.1a 进入
   训练。GoldSet 候选征集、L1 许可函与字节级特征堆栈审计是后续 Issue #11/M2.1b 的
   输入，不在本阶段执行。
