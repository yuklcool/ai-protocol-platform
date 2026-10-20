# 后端开发约定

平台整体约束见[根目录说明](../CLAUDE.md)。后端使用 Python >=3.11,<3.14、FastAPI、Google ADK；通过 `uv` 使用项目依赖。

## 当前入口

| 模块 | 职责 |
| --- | --- |
| `fast_api_app.py` | 应用、认证路由、协议端点 |
| `agents/root_runtime.py` | Root 配置、租户覆盖、授权能力组合 |
| `skills/skill_processor.py` | 单轮执行、ADK 与 AG-UI 桥接 |
| `adk/agent.py` | 模型与工具工厂、回调组合 |
| `adk/session.py` | Session、Memory、Artifact 后端及压缩配置 |
| `tools/documents/parsing.py` | 普通附件的本地格式解析 |
| `tools/documents/access.py` | 本轮附件选择、读取与权限校验 |

`app.py` 是 ADK/A2A 的部署入口，不能代替产品 Root 请求链路来证明控制台配置生效。

## 模型与协议

- Agent 使用 `resolve_model_chain`；原始 Google 结构化提取使用 `generate_content_resilient`。不绕开统一失败、重试与驻留策略。
- `tests/unit/test_model_call_reliability_guard.py` 检查新增裸模型调用。不要为了绕过失败随意扩充白名单。
- 工具 UI 通过结果映射注册并从主运行回调发出；新增流式端点必须绑定并清理 LatencyTracker。详见 [ADK 约定](adk/CLAUDE.md)。
- 用真实服务语义测试边界：`OwnershipEnforcingSessionService` 模拟非所有者读取抛错，`ScopedState` 模拟 ADK 状态前缀。
- Session 对话状态不要误写到共享 `app:` 域。压缩配置必须验证已到达真实 Runner，不能只检查工厂返回值。

## 验证

```bash
uv sync --dev --extra lint
make lint
make test-fast
```

普通单元回归不调用外部模型或 GCP；数据库、浏览器及真实 Provider 用独立门禁。按实际改动运行适用用例，保留其提交、运行及结果证据。

Ruff 的版本与 CI 对齐，修改后同时运行 check 与 format-check。测试支持代码放 `tests/support/`；防止宽松 mock 掩盖生产错误。新增参数的缺失、权限、租户与失败路径要覆盖。

运行或部署入口以 [SELFHOST](../SELFHOST.md) 和[配置流程](../docs/configuration-guide.md)为准；已有数据升级见[迁移说明](../docs/tenant-ownership-migration.md)。
