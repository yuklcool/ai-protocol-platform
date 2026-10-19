# 模型接入与 OpenAI 兼容配置

完整顺序见[配置流程第 5 节](configuration-guide.md#5-注册-provider-和模型)。运行时根据注册表 Provider 和能力标志路由，不根据模型名称是否以 `gpt-` 开头判断。

## 1. 推荐：在控制台注册

默认自托管启用数据库注册表，在 `/admin/model-providers` 完成：

1. 后端设置模型密钥，如 `.env` 的 `OPENAI_API_KEY`，用 Compose `up -d backend` 应用。
2. 创建 Provider：ID `my-gateway`、API 前缀 `https://model.example.com/v1`、密钥引用 `${OPENAI_API_KEY}`、启用。
3. 创建模型：ID `gateway-chat`、实际 API 名称、Provider、工具能力、上下文与价格。
4. 普通生成和工具调用探测均通过。
5. 保存平台默认模型及 `default/smart/fast` 映射。
6. 在 `/agent` 选择模型并保存；为目标租户允许该模型。

Provider 表单拒绝明文 Key，只接受 `${ENV_VAR}` 引用；引用缺失时明确失败，不静默改用其他凭证。新增自定义变量需显式传入容器，见[环境变量传递](configuration-guide.md#10-可选配置与环境变量传递)。

## 2. 模型 ID、API 名称与地址

| 概念 | 用途 |
| --- | --- |
| Provider ID | 平台管理网关的内部标识 |
| 模型 ID | Root、路由、白名单引用的注册表键 |
| `api_name` | 发给服务端的真实模型名称 |
| Base URL | 兼容 API 前缀，通常带 `/v1`，不含 `/chat/completions` |

| 服务 | 配置方法 |
| --- | --- |
| DeepSeek | 填服务实际地址和模型名，例如该端点暴露的 `deepseek-chat` |
| 通义/Qwen 网关 | 填所用区域/网关的兼容地址，以及实际暴露的模型名称 |
| vLLM | 填可达服务地址，如同网络 `http://vllm:8000/v1`，API 名用 served model name |
| LiteLLM | 填代理地址，如 `http://litellm:4000/v1`，API 名用代理暴露的别名 |
| OneAPI/NewAPI/内部网关 | 同样使用兼容前缀、网关凭证和已暴露模型名 |

容器内 `localhost` 不指向宿主机或其他服务。`vllm`/`litellm` 示例需要服务实际加入同一网络；默认 Compose 不会自动创建这些服务。

## 3. 能力与价格

| 配置 | 开启条件 |
| --- | --- |
| `supports_tools` | 端点可靠支持工具调用，流式路径已测通 |
| `supports_reasoning` | 服务支持平台发送的推理参数 |
| `supports_responses_api` | 实现并验证所需 Responses API 行为 |
| `supports_vision` | 模型/网关实际支持图像输入 |

通用兼容服务通常先关闭推理和 Responses API，工具能力通过实测后启用。标志不会为不支持的模型补上能力。上下文/最大输出按服务限制填写，不能机械复制示例。

价格单位是美元/百万 Token，输入和输出同时填写或同时留空。有限额度租户不能使用未计价模型；统计是估算值，Provider 未返回用量则不计入统计，不应把它当作零费用证明。

## 4. 可选：源码注册表

源码/GitOps 可编辑 `backend/config/models.yaml`。示例结构：

```yaml
models:
  gateway-chat:
    api_name: "your-upstream-model"
    provider: openai
    tier: default
    supports_tools: true
    supports_reasoning: false
    supports_responses_api: false
    residency: global
    context_window: 32768
    max_output_tokens: 8192
    description: "自定义兼容模型"
```

```env
PLATFORM_DEFAULT_MODEL=gateway-chat
OPENAI_API_KEY=替换为实际密钥
OPENAI_API_BASE=https://model.example.com/v1
```

将条目合并到现有 YAML，不要覆盖整个文件；修改镜像内 YAML 需要重新构建。`PLATFORM_DEFAULT_MODEL` 必须引用已注册模型。数据库模式下还应检查控制台保存的默认路由和 Root 选择，不能假设环境值覆盖所有已有配置。

Gemini Developer API 与 Anthropic 原生适配使用现有 YAML/运行时及 `GEMINI_API_KEY`、`ANTHROPIC_API_KEY`。动态 Provider 管理当前提供 OpenAI 兼容类型。

## 5. 验收

普通生成、真实工具调用、绑定 MCP 调用、错误配置明确报错和重启后配置持久化均需验证。v1.1.1 已有[真实 Provider 实跑](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39100531719)；新接入网关仍需在目标环境验证。
