# OpenAI-compatible model providers

The self-host runtime routes models by the registry `provider` and capability flags, not by a `gpt-*` name prefix. Any endpoint that implements the OpenAI-compatible API shape can therefore be used without changing Python source code.

The common environment variables are:

```env
OPENAI_API_KEY=your-key-or-gateway-token
OPENAI_API_BASE=https://your-endpoint.example/v1
PLATFORM_DEFAULT_MODEL=<registry-id>
```

`PLATFORM_DEFAULT_MODEL` is the **registry key**, while `api_name` is the model name sent to the remote endpoint.

## DeepSeek

```yaml
models:
  deepseek-v3:
    api_name: "deepseek-chat"
    provider: openai
    tier: default
    supports_tools: true
    supports_reasoning: false
    supports_responses_api: false
    residency: global
    context_window: 128_000
    max_output_tokens: 8_192
    description: "DeepSeek through an OpenAI-compatible endpoint"
```

Example environment:

```env
PLATFORM_DEFAULT_MODEL=deepseek-v3
OPENAI_API_KEY=your-deepseek-key
OPENAI_API_BASE=https://api.deepseek.com/v1
```

If a gateway exposes DeepSeek under a different model name, change only `api_name`.

## Qwen / DashScope-compatible gateway

Use the exact model name exposed by the OpenAI-compatible endpoint you operate:

```yaml
models:
  qwen-default:
    api_name: "qwen-plus"
    provider: openai
    tier: default
    supports_tools: true
    supports_reasoning: false
    supports_responses_api: false
    residency: global
    context_window: 128_000
    max_output_tokens: 16_384
    description: "Qwen through an OpenAI-compatible endpoint"
```

```env
PLATFORM_DEFAULT_MODEL=qwen-default
OPENAI_API_KEY=your-qwen-or-gateway-key
OPENAI_API_BASE=https://your-qwen-compatible-endpoint.example/v1
```

For providers that expose a reasoning-specific Qwen model, create a separate registry entry and set `supports_reasoning` to match the endpoint contract instead of inferring it from the name.

## vLLM

A local or remote vLLM server normally exposes an OpenAI-compatible model identifier. Keep the registry key stable and set `api_name` to the identifier returned by the server's model-list endpoint.

```yaml
models:
  vllm-local:
    api_name: "your-served-model-name"
    provider: openai
    tier: default
    supports_tools: true
    supports_reasoning: false
    supports_responses_api: false
    residency: local
    context_window: 32_768
    max_output_tokens: 8_192
    description: "Model served by vLLM"
```

When vLLM runs on the same Docker network, use the service name rather than `localhost`:

```env
PLATFORM_DEFAULT_MODEL=vllm-local
OPENAI_API_KEY=local-placeholder
OPENAI_API_BASE=http://vllm:8000/v1
```

`localhost` inside the backend container points to the backend container itself, not to another Compose service.

## LiteLLM Proxy

```yaml
models:
  litellm-default:
    api_name: "general-chat"
    provider: openai
    tier: default
    supports_tools: true
    supports_reasoning: false
    supports_responses_api: false
    residency: global
    context_window: 128_000
    max_output_tokens: 16_384
    description: "Model routed through LiteLLM Proxy"
```

```env
PLATFORM_DEFAULT_MODEL=litellm-default
OPENAI_API_KEY=your-litellm-master-or-virtual-key
OPENAI_API_BASE=http://litellm:4000/v1
```

The same pattern applies to OneAPI, NewAPI and internal model gateways: the platform only needs an OpenAI-compatible endpoint plus a registered model entry.

## Capability flags

Do not copy capability flags blindly. They define runtime behavior:

```yaml
supports_tools: true
supports_reasoning: false
supports_responses_api: false
```

- `supports_tools`: enable only when the endpoint/model reliably supports tool/function calling.
- `supports_reasoning`: enable when the provider contract supports the reasoning controls used by the platform.
- `supports_responses_api`: enable only when the endpoint implements the required Responses API behavior; most third-party OpenAI-compatible gateways should leave this `false` unless verified.

For a generic OpenAI-compatible provider, the safest starting point is `supports_tools: true`, `supports_reasoning: false`, `supports_responses_api: false`, then enable additional capabilities after a real integration test.

## Acceptance test

After adding the registry entry and environment values:

```bash
make docker-up
make selfhost-smoke
```

Then verify through the browser:

1. normal chat returns a model response;
2. a Runtime Skill can invoke at least one tool;
3. a failed provider/model name returns an explicit error instead of silently switching providers;
4. restart the backend and confirm the configured self-host state remains durable.

Issue #2 should only be considered fully complete after at least one non-OpenAI OpenAI-compatible endpoint has passed a real Agent + Tool Calling path. Unit/registry tests alone do not replace that final integration acceptance.
