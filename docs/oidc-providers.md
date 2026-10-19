# OIDC 提供商配置示例

先阅读[OIDC 接入](selfhost-oidc.md)，创建本地授权账号并关联 `issuer + sub`。外部声明不会自动创建租户或授予管理员权限。

## 1. Keycloak 配置

仓库提供开发测试用 `docker-compose.keycloak.yml` 和 `examples/oidc/keycloak/realm-export.json`，镜像固定为 Keycloak 26.7.4。示例导入 realm/client `ai-protocol-platform`，使用公开客户端、Authorization Code + PKCE S256，回调为 `http://localhost:3456/auth/oidc/callback`，示例用户为 `oidc-admin` / `owner@example.com`。

```bash
docker compose -f docker-compose.keycloak.yml up -d
```

这条命令只启动可选 IdP，默认应用 Compose 不自动启动 Keycloak。不要将开发示例账号与配置直接作为生产登录环境。

真实部署使用浏览器和后端均可达的 HTTPS 域名：

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://sso.example.com/realms/ai-protocol-platform
OIDC_CLIENT_ID=ai-protocol-platform
OIDC_AUDIENCE=ai-protocol-platform
OIDC_REDIRECT_URI=https://ai.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_CLIENT_AUTH_METHOD=none
```

机密客户端按配置改用 `client_secret_basic` 或 `client_secret_post` 并传入后端 secret。

## 2. Microsoft Entra ID 配置

创建应用注册，配置与平台完全一致的 Web 回调。单组织部署使用租户专属 v2 issuer：

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://login.microsoftonline.com/替换为租户ID/v2.0
OIDC_CLIENT_ID=替换为应用client-id
OIDC_AUDIENCE=替换为同一client-id
OIDC_REDIRECT_URI=https://ai.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_CLIENT_AUTH_METHOD=client_secret_post
OIDC_CLIENT_SECRET=替换为真实secret
```

不要在预期单一企业租户时直接使用 `common`。平台仍依据已验证 subject 的显式映射决定本地租户/权限。

## 3. Okta 配置

创建 OIDC Web Application，登记回调；自定义授权服务器示例：

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://your-okta-domain.example/oauth2/default
OIDC_CLIENT_ID=替换为client-id
OIDC_AUDIENCE=替换为同一client-id
OIDC_REDIRECT_URI=https://ai.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_CLIENT_AUTH_METHOD=client_secret_basic
OIDC_CLIENT_SECRET=替换为真实secret
```

若实际 discovery 的 issuer 不同，以真实值为准；比较只规范化末尾斜杠，不会自动适配其他 issuer。

## 4. 关联和兼容验证

```bash
cd backend
uv run python scripts/link_oidc_subject.py \
  --issuer https://sso.example.com/realms/ai-protocol-platform \
  --subject 替换为真实外部sub \
  --email owner@example.com
```

脚本使用当前数据库配置，应先在副本验证。仓库 `.github/workflows/oidc-keycloak-compatibility.yml` 启动真实 Keycloak，验证签名 ID token、discovery、JWKS、issuer/audience、subject 映射和本地权限重载；其他 IdP 与目标租户仍需实际验收。
