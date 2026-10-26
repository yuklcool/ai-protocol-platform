# 照明查询交互接入说明（#152）

## 当前交付边界

平台增加六种照明结果的受控契约、A2UI 结果映射及统一宿主视图。入口仍是现有聊天,结果按需进入 Workbench;不新增场景侧栏、任务入口、Runtime、聊天通道或 HTML 执行能力。

设计基准是 [2026-10-26 原型](../outputs/lighting-a2ui-2026-10-26/index.html)及[说明](../outputs/lighting-a2ui-2026-10-26/README.md),原始固定提交为 `a62e1d717acb9b981800297dbcfc79de8adcdb4d`。本次复用 `SeriesArtefactTab` 的图表、排序比较和 CSV 序列化,宿主按结果类型分发,没有给每个 Skill 建立单独页面。

**新增的 `query_lighting` 是接入契约,不是仓库已有的生产 SQL 工具。** 生产照明 Skill、SQL MCP 的真实返回样本、在线/亮灯规则、历史归属与数据权限配置尚未随仓库提供。当前实现用合成 MCP 做协议验收,不能据此声称生产技能已连通、原型已完整验收或部署已升级,也不能关闭 #152。

## 接入现有技能与 MCP

1. 在可信只读服务侧提供 `query_lighting(request: object)` 适配入口,复用现有照明技能的查询。不要让模型把自由 SQL 或计算结果作为展示参数提交。平台没有增加可由模型填写事实的渲染工具。
2. 适配服务验证调用方设备范围、历史归属和业务权限。Root/MCP 授权只证明用户可以调用服务,**不能替代业务数据库的设备 ACL**。静态 MCP 凭据不会自动完成用户到业务身份的映射;未完成该映射前不得向多用户开放生产查询。
3. 在现有 MCP 管理页配置服务,测试连接、发现 `query_lighting`,绑定 Root。使用既有凭据引用,不把密钥放入 Skill、结果或浏览器。
4. 绑定已授权照明 Skill,指导模型选择场景并补齐首次查询参数。统计、单位、过滤、缺口与报告正文由受控服务返回。
5. 要启用立即追查,在 Root 交互设置启用 A2UI、上下文写入与动作触发运行。关闭时服务端拒绝按钮请求。调整参数只进入消息草稿,由用户检查后发送。

| 场景值 | 沿用业务技能 | 适配服务责任 |
| --- | --- | --- |
| `night` | `single-lamp-operation-report`、`night-operation-analysis-with-fallback-sources`、`night-report-time-window` | 跨日窗口、样本覆盖、未解除报警、夜间能耗、原九章报告 |
| `lamp_alarms` | `single-lamp-alarm-analysis`、`alarm-batch-pattern-diagnosis` | 独立事件、恢复历史、同杆/同回路证据 |
| `rtu` | `rtu-operation-report`、`smartlight-rtu-online-analysis` | `sl.r_his_coplog_phase` 历史巡测、生产判定配置、原七章报告 |
| `rtu_alarms` | 既有缺相、过流、断路、漏电专项技能 | 相位/支路、电参、保护动作与专项证据 |
| `energy` | `rtu-energy-anomaly-screening`、`diagnose-energy-spike-by-duration-decomposition`、`smartlight-energy-saving-rate-analysis` | 夜间、7 日日报、30 日上升波动、7 日节能率四种口径 |
| `reconcile` | `rtu-lamp-energy-inversion-query` | D 日报、逐灯过滤、主挂载链路、覆盖与明细 |

生产 Skill 与固定查询没有被本次改写,适配时需要核对其当前版本,不能用 CI fixture 替换生产实现。

## 结果契约

严格模型见 [`backend/lighting/results.py`](../backend/lighting/results.py)。返回 `schema_version: "lighting-query/v1"`,接受结构化 JSON、MCP `structuredContent`、单文本 JSON 或既有 `result` 包裹。错误、无法判定的多文本块、格式缺失、超过 2 MB 的 UI 载荷均显示失败,不变成零报警。

| 字段 | 要求 |
| --- | --- |
| `scene`、`status` | 六场景之一;状态为 `success / partial / empty / error` |
| `query` | 查询 ID、范围、IANA 时区、带偏移起止时间、截止与生成时点、来源、覆盖、过滤、缺失说明 |
| `query.basis` | `night / daily / historical`;日报必须是时区内自然日 00:00 边界且 `report_type: "D"` |
| `query.rtu_energy_window` | 单灯改到 06:00 时保留 RTU 到 07:00 的独立窗口,追查时继续携带 |
| `columns`、`rows` | 声明列及最多 1000 个已返回对象;单灯、RTU、回路、灯杆、报警 ID、相位、锚点、历史窗分别保存 |
| `row_count`、`complete` | 查询范围条数及是否完整;截断清单不能冒充范围汇总 |
| `metrics` | 服务端统计、单位和口径;前端筛选不改写汇总 |
| `chart` | 服务提供坐标、数据与可选清单联动字段;缺失不补零、不插值 |
| `rows[].evidence` | 读数、单位、样本时点、来源、解释;未取得证据时明确提示 |
| `rows[].relationship_verified` | 服务已核对历史主挂载链路;默认 false,未验证时拒绝跨层级查询 |
| `actions` | 唯一编号、白名单意图、关联行编号、可选能耗视图;不接受脚本、SQL、HTML、自由提示词 |
| `report` | 服务返回完整固定报告;单灯/RTU 运行报告校验原章节顺序,不由 UI 编造缺失正文 |

合成返回构造器见 [`backend/tests/fixtures/lighting_results.py`](../backend/tests/fixtures/lighting_results.py)。首次自然对话输入由只读服务定义;按钮追查的 `request` 则从服务器保存结果重建。

适配服务应在返回 MCP 结果前完成计算,让模型和宿主收到相同事实。Python 适配可调用 `normalize(LightingResult.model_validate(result)).model_dump(mode="json")`;CI MCP fixture 也遵循此顺序。宿主映射再次校验为幂等操作,不会重复添加统计或缺口,模型无需从原始行自行计算节能率和差额。

| 固定计算 | 字段与规则 |
| --- | --- |
| 截止时点报警 | `triggered_at / restored_at / history_complete`;只有可还原历史才判恢复,不从当前末态反推;证据窗默认前后各 10 分钟 |
| 夜间时长拆分 | `previous_kwh / actual_kwh / previous_minutes / minutes / matched`;仅同一批有效配对、基准时长 >0 参与;长时低耗只标线索 |
| RTU 上升波动 | `previous_kwh / actual_kwh`;有效值 <1500,同时增加 ≥50 kWh 且 ≥30%;前日零或缺失不计算比率 |
| 加权节能率 | `theoretical_kwh / actual_kwh / target_rate`;完整返回时先合计有效配对能耗再计算,披露有效数;缺目标不判达标 |
| 日报对账 | `lamp_kwh / rtu_kwh / lamp_filter_applied`;业务服务执行逐灯 0≤kWh<100 过滤,平台要求已确认过滤及主链路,RTU 0≤kWh<1500;有效零分母仍显示差额,比值为空;缺失或关系不明不判倒挂 |

对账主链路是单灯 → `r_rturoad` → `r_road_switch` → 控制箱 → RTU,不能改用变压器关系。服务应返回回路/单灯明细与抄表时刻证据,不能按比例构造分项。平台校验可信结果中的声明,没有连接业务数据库独立证明该链路。

RTU 专项报警分别列出必要证据缺口。漏电 ≤1 A 不认定安全;缺动作记录不认定动作失败;过流缺额定值时比例为空;缺相与断路保留多项核查。生产在线/亮灯判定、历史恢复能力、日报覆盖、异常范围与保护定值由既有服务负责,平台不新增生产阈值。

## 动作、协议与恢复

`query_lighting` MCP → 主 Agent `after_tool_callback` → 注册转换 → AG-UI `A2UI_SURFACE` → `SurfaceRegistry` → `ChatShell` → 共用宿主视图。当前清单搜索、筛选、排序、已有证据、CSV 与报告查看均是本地读操作。CSV 仅导出当前过滤的已返回清单,保留缺失与零值区别,防止文本公式执行。

远端追查复用 `useActionDrivenAgent` 和 `/api/agent/stream`。浏览器只提交 `run:lighting.query` 与 `actionId`。服务端验证会话所有者、Root 授权、来源 MCP、保存动作白名单、24 小时有效期与历史归属,丢弃浏览器快照,重建设备/报警/相位、原时间窗和锚点。工具边界再次检查 MCP 授权,将模型参数替换为规范请求,禁止此动作轮次调用其他工具。业务服务仍须重新检查设备 ACL。

查询中同步阻止重复点击,传输使用持久化 requestId 防重。失败允许显式重试;停止与断线不自动重发。刷新恢复原时点结果,不会执行查询;恢复后的远端按钮只读,可将参数放入草稿。普通聊天清除上一轮照明动作信号。

能耗切换由服务端同步重建时间口径与窗口。以保存的截止时点为固定锚点,不超过原生成时点:夜间取最近已完成的 18:00–07:00,周报与节能率取之前 7 个完整自然日,上升波动取 30 日;自然日使用查询时区及 D 日报,不沿用夜间 RTU 独立窗口。设备范围、来源查询与截止时点继续保留。同视图读取和重试保留用户原始窗口,包括单灯 06:00 / RTU 07:00 的分别取值。

手机打开照明结果后,结果占据主要内容区,收起上方聊天输入和附件栏;结果标题旁的“继续提问”返回并聚焦原消息草稿。参数草稿同样返回聊天且不自动发送。桌面继续使用对话与结果双栏。

输出固定为平台 **A2UI v0.9** 与 `https://a2ui.org/specification/v0_9/basic_catalog.json`。Basic 组件树提供回退,精细表格/图表/抽屉由宿主读受控数据模型显示。未增加自定义 Catalog 或全平台协议升级;旧服务器 Skill 的 v0.9.1 与另一 Catalog 地址不能原样透传。

## GitHub 验证及未完成项

按 #152 要求,本地不运行测试、lint、typecheck、构建、服务或浏览器,检查全部在 Actions：

- 常规 CI: 后端质量、业务规则、授权及前端交互回归。
- Model provider gate: 生产前端构建、真实 JWT / PostgreSQL / ADK / MCP / A2UI 链路;模型选择与读数明确使用合成 fixture。
- 浏览器: 六场景/四能耗口径、清单/CSV/抽屉、追查上下文、防重、篡改拒绝、刷新无重放与草稿;1440、768、390 档结果、抽屉和原型对照截图上传到该次 `model-root-skill-*` 产物。

截图用于人工核对,不代表像素一致性自动通过。仍需生产 Skill/返回适配、设备 ACL、历史归属、真实模型/MCP、所有原型追查路径与视觉/键盘完整验收。内网联调用有授权和网络条件的 GitHub 自托管 Runner,不回退本地测试。实现 PR 使用 `Part of #152`;必要验收全部完成且进入 main 后才能关闭,合并、镜像与目标部署另行记录。
