# A2UI / AG-UI 配置与操作验收

支持契约为 **A2UI v0.9 + SDK basic catalog**。前端用 `@ag-ui/client` 消费事件；后端锁定 `ag-ui-adk==0.6.5`、`google-adk==1.31.1`。不宣称其他 A2UI 版本或任意未注册组件目录兼容。

## 1. 配置前提

1. 按[完整配置流程](configuration-guide.md)配置认证、持久卷、前端与沙箱源并登录。
2. 注册真实 Provider/模型，普通生成与流式工具调用探测成功，凭证保留后端。
3. 在 `/agent` 选择模型、绑定授权 Skill/Tools/MCP，完成工具规则后启用 fail-closed 权限。
4. 同时开启 A2UI、上下文写入和操作触发运行，保存。
5. 从 `/chat/root-agent` 测试。Skill 编辑器管理内容，不独立配置第二个 Agent，见[模块边界](module-simplification.md)。

普通聊天和界面操作共用 `/api/agent/stream` 及当前 Root 策略，旧 Skill 流接口保留为兼容入口。独立 surface-action-run 用于协议客户端与开发预览，同样执行 Root 策略。

自托管标题默认取首轮用户文字，不额外调用 Gemini；仅显式设置 `CHAT_TITLE_MODEL` 才启用可选模型标题。该变量需显式传入 backend，客户端遵守 `GOOGLE_GENAI_USE_VERTEXAI`。

## 2. 必须通过的操作

| 操作 | 合格证据 |
| --- | --- |
| Provider 和模型 | 普通生成、工具调用探测成功 |
| 产品 Chat 调用 MCP | 真实模型调用 `show-map` 等实际工具，MCP App 渲染 |
| 生成 A2UI 表单 | 模型经受校验工具输出界面，不以预置界面代替 |
| 输入和点击 | 浏览器真实事件到达当前 Root Session |
| 继续运行 | AG-UI 传递运行、工具、文本/状态与 A2UI patch |
| 刷新 | 从 PostgreSQL 恢复表单、输入值和结果 |
| 再次操作 | 恢复表单仍可交互并接收新更新 |
| 返回普通聊天 | 不残留操作触发状态，能继续正常对话 |
| 失败或截断 | 界面显示错误，不误报成功 |
| 停止操作 | 共享运行被取消，控件恢复可用 |
| 租户隔离 | 相同 UID 不能跨租户复用 Session、Memory、app/user state 或工具 |

模型和工具生成的界面共用 `A2UI_SURFACE` 与持久化 surface registry。只有界面、没有额外文字也可以是有效结果。patch 需保留创建历史，删除/重建按消息顺序回放；普通表单恢复后可操作，一次性确认卡仍按一次性语义处理。

## 3. 自动化验收与证据

`Protocol operation acceptance` 工作流同时运行真实浏览器 Provider 验收与 Tenant A/B 验收。配置仓库变量 `REAL_PROVIDER_BASE_URL`、`REAL_PROVIDER_MODEL` 及 Actions secret `REAL_PROVIDER_API_KEY`；手动工作流也支持显式输入，见[真实 Provider 验收](real-provider-acceptance.md)。

确定性的 `A2UI live self-host acceptance` 验证预置 surface 持久化，不能替代模型生成表单测试。PR 的语法检查、跳过任务、mock 模型、旧提交或未发布代码也不能作为发布实跑证据。

v1.1.1 的[真实操作工作流](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100531719)已成功；[发布镜像工作流](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100933295)同为提交 `29688543e0b4c1749210a8be90b0c94a207ca87e`。记录应区分单元测试、真实数据库/浏览器、真实 Provider、正式镜像，以及目标部署现场结果。

真实成功流程不自动证明目标域名下的异常、截断、取消和代理流式行为，部署后仍按表逐项验证。

## 4. 已有 PostgreSQL 部署

保留现有卷并先备份。ADK Session 存储 app namespace 现在绑定可信租户；Memory 绑定 tenant/app/UID，运行时仍返回逻辑 app 名 `root-agent` 或保存的旧 app 名。

无归属旧 Session/Memory 不参与自动回退搜索。必须依据权威 Session 索引及 tenant ownership 独立审核迁移，不能按邮箱猜测。metadata ownership 工具不代替存储 namespace 搬迁。

目标部署需完成迁移、验证和回滚演练后，再验证旧会话、表单与记忆继续可用。[Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 保留此边界，见[迁移手册](tenant-ownership-migration.md)。
