# 全站浅色界面验收

本次范围为 #122，基于 #125 的文件分析和 #126 的模型接入流程验证最终组合效果。两个前置 PR 已分别合并，界面改版由 #128 独立审阅和合并。

## 页面清单

浏览器用例 `frontend/e2e/ui-responsive-live.spec.js` 使用真实 local-jwt 登录和后端 API，不拦截或伪造接口。每个路由在 1440×1000、768×1024、390×844 下检查浅色主题、页面级横向溢出并保存截图。

| 路由 | 核对内容 |
| --- | --- |
| `/` | 公开首页、协议入口卡片、状态、登录弹窗 |
| `/auth/oidc/callback` | 登录拒绝/缺少参数的错误反馈 |
| `/chat/root-agent` | 对话、输入区、附件标签、文件与历史侧栏、工作区 |
| `/agent` | Root 设置、窄屏分区选择、宽屏编辑及预览 |
| `/skills` | 列表、加载与空状态、进入 Studio |
| `/skills/studio/new` | 编辑器、可换行工具栏、配置控件 |
| `/admin` | 管理入口与权限状态 |
| `/admin/users` | 用户列表、创建表单、Agent 策略 |
| `/admin/users` | 用户列表、表单、有效权限 |
| `/admin/groups` | 权限组列表、资源勾选 |
| `/admin/mcp-servers` | 服务、诊断、错误、工具/资源/应用信息 |
| `/admin/model-providers` | 服务列表、添加服务、模型选择、测试、Root 应用 |
| `/admin/analytics` | 筛选、会话列表、详情、用量 |
| `/admin/audit` | 审计列表、筛选与详情 |
| `/admin/settings` | 平台说明与压缩配置 |
| `/dev/a2ui` | A2UI 动态组件容器与原有事件链路 |
| `/dev/mcp-apps` | 开发入口与说明 |
| `/dev/mcp-apps/active` | MCP Apps 外层卡片和通知桥接操作 |
| `/dev/mcp-apps/passive` | MCP Apps 外层卡片和失败提示 |
| `/group` | 当前认证模式提示，匿名分组表单沿用既有认证逻辑 |

截图覆盖默认页面状态，不代表每个路由所有状态都已逐一做图像差异验证。OIDC 错误定位在主内容区，避免误匹配框架路由播报区；上传用例等待能力配置完成后再选择文件。加载/空/错误、权限拒绝、撤销、表单保存与失败主要结合已有组件测试和功能浏览器用例检查。第三方 iframe 内部页面不纳入宿主样式一致性要求。

## 关键操作

- 响应式用例：手机打开导航、Escape 关闭、焦点返回、切换模型页、填写服务表单；对话文件侧栏打开和关闭。轮询页面按标题或编辑控件就绪验收，不等待网络空闲。
- `root-console-live.spec.js`：用户账号、权限组、知识、撤销及普通成员拒绝。
- `model-setup-live.spec.js`：模型服务接入、测试、重测、刷新、手机表单、产品对话发出实际 HTTP 模型请求。
- `chat-files-live.spec.js`：真实附件上传、解析、选择、移除、刷新恢复与会话隔离。
- 原 MCP 与 A2UI 端到端门禁：真实工具/资源请求、动作提交、持久化与刷新恢复。

HTTP 测试 Provider 只证明产品调用链路，不证明外部模型质量。缺少外部 Provider 凭据时真实模型用例继续明确跳过，#118、#119 不因此关闭。

## 结果与证据

- 原始样式参考及三种视口预览：[frontend-style-kit](frontend-style-kit/README.md)。
- 本地前端类型检查、生产构建及 1,180 项回归通过；最新提交的完整结果和截图链接统一记录于 [PR #128](https://github.com/yuklcool/ai-protocol-platform/pull/128)。
- 本地 Chromium 下载成功，但运行环境拒绝浏览器所需的 socket 系统调用，无法在本地完成截图验收。浏览器实际操作与截图由 Actions 的 PostgreSQL/Chromium 环境执行，结果必须在 PR 中链接。
- 截图、协议测试 Provider 的请求证据、失败信息保存在对应 Actions artifact；少量不含个人信息的测试页面预览写入验收日志，供复查。
- 历史数据迁移、目标安装恢复与回滚继续按 #9 验收；本次不新增旧主题或配置兼容。
