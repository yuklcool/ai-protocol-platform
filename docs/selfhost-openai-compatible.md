# 模型接入与 OpenAI 兼容配置

完整顺序见[配置流程第 5 节](configuration-guide.md#5-注册-provider-和模型)。运行时根据注册表 Provider 和能力标志路由，不根据模型名称是否以 `gpt-` 开头判断。

## 1. 推荐：在控制台注册

当前源码的自托管控制台在 `/admin/model-providers` 提供分步接入：

1. 在后端配置 `.env` 的 `OPENAI_API_KEY`，用 Compose `up -d backend` 应用环境变更。
2. 点击“添加模型服务”，填写中文名称、API 根地址、后端密钥变量名 `OPENAI_API_KEY`。只填变量名，不填密钥或 `${}`。
3. 从服务列表选择模型，或手动填写实际模型名称；内部 ID 自动生成。高级能力、输出限制和价格按实际服务填写。
4. 运行普通生成和工具调用两项测试，阅读中文结果及排查提示。
5. 两项均通过后点击“用于平台 Root”；单模型无需配置层级映射。
6. 检查当前用户实际模型和权限，再从“开始对话”验证真实调用。

v1.1.1 镜像尚未包含此改版，原页面仍需手动填写 Provider/模型 ID，并在 `/agent` 选择该模型保存。以上新流程须部署包含改版的源码或后续镜像。

密钥始终只在服务端解析：页面会把变量名转换成 `${ENV_VAR}` 引用提交，接口拒绝明文密钥。变量缺失时明确失败，不静默改用其他凭证。自定义变量需显式传入容器，见[环境变量传递](configuration-guide.md#10-可选配置与环境变量传递)。

测试记录绑定当前配置及密钥，在 24 小时内有效，刷新可恢复。修改调用配置后重测再应用。应用只改 Agent 模型，保留公共能力和用户个人设置；个人 Skill 不选择模型。文本和工具接入测试不代替图片、真实流式对话或 MCP 的实际验收。

## 2. 模型 ID、API 名称与地址

| 概念 | 用途 |
| --- | --- |
| Provider ID | 自动生成的服务内部标识，无需用户命名 |
| 模型 ID | 自动生成，供 Root 和路由引用的注册表键 |
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

价格单位是美元/百万 Token，输入和输出同时填写或同时留空。统计是估算值，Provider 未返回用量则不计入统计，不应把它当作零费用证明。

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
