# 浙江标签与本地派生数据权利矩阵 v0（M2.1a2 / Issue #12 §26–29）

- 代码：[rights.py](file:///data/yingda/Spartina-Earth/src/spartina/data/zhejiang/rights.py)
- 产物：`datasets/manifests/zhejiang_label_rights_v0.{csv,parquet}`、
  `zhejiang_label_rights_v0.fingerprint.json`
- 20 个资产行；registry fingerprint
  `4b5d46b1a4e248bb4e27c071bf87f9984e5350d4218a3bc73a5bc5da5ae4e9e2`
- 证据获取日期：**2026-10-02**（全部为真实抓取，无口头许可、无推断）

## 1. 为什么拆成八个字段

M2.1a 把"能否用于训练"与"能否公开再分发"混成一个布尔标志。M2.1a2
拆为 8 个独立字段，取值仅 `YES / NO / UNKNOWN`。**UNKNOWN 表示
"许可证文本未涉及该用途"，永远不自动升级为 YES 或 NO。**

字段：`scientific_analysis_allowed`（科研分析）、
`internal_training_allowed`（内部模型训练）、
`validation_use_allowed`（验证用途）、
`public_redistribution_allowed`（原样公开再分发）、
`derived_model_release_status`（含模型权重的派生品发布）、
`citation_required`（署名要求）、`permission_evidence`（证据原文）、
`license_source`（来源）。另含 `rights_status`
（AUDITED_TEXT_SUPPORTED / NO_LICENSE_TEXT_LOCATED_ALL_UNKNOWN）。

三条不可推断原则：

1. **禁止再分发 ≠ 禁止内部科研/训练**——文本没说训练就是 UNKNOWN，
   不是 NO；
2. **本地有文件 ≠ 有许可证**——存在性不授予任何权利；
3. **数据开放 ≠ 模型权重可发布**——权重/派生品是独立问题，
   USGS/Copernicus 文本均无模型条款 → UNKNOWN。

## 2. 逐条决定

| 资产 | 层级 | 分析 | 内部训练 | 验证 | 再分发 | 模型发布 | 署名 |
|---|---|---|---|---|---|---|---|
| **L1** geodata.cn 2015 全国栅格 | SILVER | YES | **UNKNOWN** | YES | **NO** | UNKNOWN | YES |
| **L2** CM-SSM 2020 面 | WEAK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **L3** 杭州湾 mask 2015 | WEAK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **L4/5/6** CMSA 面 2019/2020/2021 | WEAK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **U1/U2/U3** HZB L8 2015 本地合成（全波段/NDVI/SAI） | UNLABELED | YES | YES | YES | UNKNOWN* | UNKNOWN | YES |
| **U4/U5** HZB S1 VV/VH 2015 本地栅格 | UNLABELED | YES | YES | YES | UNKNOWN* | UNKNOWN | YES |
| **U6/U7** 浙江 feature stack A/B | UNLABELED | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| **U8** YQB S2 合成 2019–2025（×7 年） | UNLABELED | YES | YES | YES | UNKNOWN* | UNKNOWN | YES |

\* 上游原始数据许可证开放，但**本地合成的生产链（日期、处理、输入）
不可验证**，再分发/模型发布保留 UNKNOWN，不因其上游开放而推断。

汇总：13 行 AUDITED_TEXT_SUPPORTED（L1 + 12 行上游开放），
7 行 NO_LICENSE_TEXT_LOCATED_ALL_UNKNOWN（L2–L6、U6、U7）。

## 3. 证据原文与来源（2026-10-02 获取）

### 3.1 L1 geodata.cn（DOI 产品页）

- 来源：`https://www.geodata.cn/data/datadetails.html?dataguid=65372070926827`；
  DOI `10.12041/geodata.65372070926827.ver1.db`
- 原文要点："**仅限科学研究使用**"；未经平台书面许可禁止复制、
  传播、转载、销售；要求必须注明数据来源并致谢。
- 推理链：科研分析=YES（明确授权）；验证=YES（科研范围内）；
  再分发=NO（明确禁止）；**内部训练=UNKNOWN、模型权重=UNKNOWN**
  （文本未涉及机器学习训练与权重发布，既不许可也不禁止）。
- 行动：可用于内部科学分析与验证；任何对外发布（含数据集镜像、
  权重随数据条款发布）前必须取得书面许可。

### 3.2 USGS / Landsat（U1–U3 上游）

- 来源：`https://www.usgs.gov/centers/eros/data-citation`
- 原文要点：多数 USGS/NASA EROS 数据（含 Landsat）属
  **public domain**，"may be used, transferred, or reproduced without
  copyright restriction"；建议致谢 "courtesy of the U.S. Geological
  Survey"。
- 推理：分析/训练/验证=YES；本地派生品再分发与模型发布因本地生产链
  不可验证=UNKNOWN；署名=YES（请求而非强制，按请求执行）。

### 3.3 Copernicus Sentinel（U4/U5 的 S1、U8 的 S2 上游）

- 来源：Copernicus Sentinel Data Legal Notice
  `https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice`
  （EU Reg 377/2014；Commission Delegated Reg 1159/2013 Art. 7–8，
  ECMWF 镜像 PDF 获取全文）
- 原文要点：free, full and open access；为任何合法用途授予复制、
  分发、传播、改编/修改/组合权利；强制声明
  "**Contains modified Copernicus Sentinel data [Year]**"；
  无模型权重条款。
- 推理：分析/训练/验证=YES；模型权重/本地合成品再分发=UNKNOWN
  （无文本 + 本地链不可验证）；署名=YES。

### 3.4 无许可证文本（L2–L6、U6、U7）

- 检索后未定位到任何许可证/使用条款文本 → 全部字段 UNKNOWN，
  包括"分析"与"署名"。UNKNOWN 不是禁止，但在书面确认前：
  不对外再分发、不声称可商用、不用于可发布模型权重链；
  内部复现实验可以继续（仓库内只读保留），结果发表时标注
  许可状态 UNKNOWN 并设法联系权利人。

## 4. 与后续闸门的接口

- 训练清单生成器必须逐字段过滤：内部训练只看
  `internal_training_allowed == YES`，不得用"分析=YES"替代；
- 任何对外产物（数据样本、附录、SpartinaGuard 交付）按
  `public_redistribution_allowed` 与 `derived_model_release_status`
  双重过滤；
- 署名要求在 M2.1b 产物 provenance 模板中落地（USGS 致谢 +
  Copernicus 声明 + geodata.cn 来源标注）；
- UNKNOWN 的解锁路径：取得书面许可 → 更新证据、日期、指纹；
  禁止口头/邮件转述替代文本证据。

## 5. 未决事项（MISSING / UNKNOWN，不猜测）

- L1 是否允许 ML 训练与权重发布：UNKNOWN，待 geodata.cn/数据权利人
  书面回复；
- L2–L6、U6、U7 权利人、许可文本、联系方式：MISSING，待资产追查
  （见 [ZHEJIANG_LABEL_INVENTORY_V0.md](ZHEJIANG_LABEL_INVENTORY_V0.md)）；
- U1–U5、U8 本地合成的确切生产链与来源景：UNKNOWN，在 M2.1b
  provenance 中以原始 GEE 重生产替代本地合成后才可解除。
