# 可选 OIDC 企业身份认证

默认自托管使用 `local-jwt`。需要 Keycloak、Authentik、Dex、Entra ID、Okta 等企业身份源时，可选择 OIDC。提供商示例见[OIDC 配置示例](oidc-providers.md)。

## 1. 支持能力与边界

支持 discovery、JWKS 短期缓存、签名/issuer/audience/时间校验、Authorization Code + PKCE、服务端保存并一次性消费 state/nonce/verifier，以及公开客户端或机密客户端认证。

后端执行 code exchange，浏览器不获取 client secret/PKCE verifier，也不需要直接跨域调用 IdP token endpoint。验证后的 ID token 保存在 `sessionStorage`，到期重新登录，当前没有静默 refresh-token 流程。

IdP 负责认证，平台 PostgreSQL `auth_users` 负责用户和角色。外部邮箱、`user_id`、`groupTags` 或 `role` 声明不会自动创建用户/管理员；必须显式关联 `issuer + sub`。

## 2. 切换前准备本地授权记录

先在 `local-jwt` 模式创建平台账号与角色，记录将关联的邮箱/UID。通过 IdP 获取真实 subject 后关联：

```bash
cd backend
uv run python scripts/link_oidc_subject.py \
  --issuer https://id.example.com/realms/platform \
  --subject 替换为真实外部sub \
  --email owner@example.com
```

命令必须连接正确的持久化数据库；镜像部署可在对应 backend 容器内运行。无映射、账号停用或 UID 变化时认证拒绝。不要临时猜测邮箱归属来绕过映射。

OIDC 模式的账号生命周期由外部 IdP 管理，控制台不会伪装为本地密码管理。切换前准备并验证授权记录，避免切换后没有可登录管理员。

## 3. 环境配置

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://id.example.com/realms/platform
OIDC_CLIENT_ID=ai-protocol-platform
OIDC_AUDIENCE=ai-protocol-platform
OIDC_ALLOWED_ALGORITHMS=RS256
OIDC_REDIRECT_URI=https://ai.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_TRANSACTION_TTL_SECONDS=300
OIDC_CLIENT_AUTH_METHOD=none
```

浏览器 PKCE 用 ID token 作为会话凭证，`OIDC_AUDIENCE` 应与 `OIDC_CLIENT_ID` 一致；省略时默认取 client ID。scopes 包含 `openid`，不允许算法 `none`。

机密客户端按 IdP 要求改为 `client_secret_basic` 或 `client_secret_post` 并设置 `OIDC_CLIENT_SECRET`，密钥只留在后端。必要时可用 `OIDC_DISCOVERY_URL` 指定 discovery。

Compose 用 `up -d` 应用变更；源码前端认证模式属于构建参数，切换时重建前端。发布镜像启动时支持认证模式替换。

## 4. 登录流程

浏览器调用 `/api/auth/oidc/start`，后端创建一次性事务并跳转 IdP；IdP 回调 `/auth/oidc/callback`，浏览器把 code/state 交后端。后端消费 state、兑换并校验 ID token，然后通过映射加载 `auth_users` 的可信用户与角色。

`GET /api/auth/provider` 返回非秘密配置、能力及可达 discovery 的端点，不返回 client secret。浏览器和后端都必须能访问配置的 issuer；不要混用不同主机名导致 issuer 不匹配。

## 5. 验收

测试真实登录/回调、刷新恢复、过期重新登录、未关联 subject 拒绝、禁用账号拒绝、外部伪造管理员声明不能提升权限。还需验证目标用户资源隔离。

仓库包含真实 Keycloak 兼容工作流；它不自动证明每个 Entra ID/Okta 用户配置已经验收。外部 IdP 配置和目标环境网络需要单独验证。
