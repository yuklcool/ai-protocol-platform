# 使用版本化镜像部署

本文适用于不克隆源码、直接拉取 GHCR 镜像的部署。第一次配置参见[完整配置流程](configuration-guide.md)，源码构建参见[自托管说明](../SELFHOST.md)。

## 1. 发布物与版本

每个稳定版本发布三个应用镜像，均包含 `linux/amd64`、`linux/arm64`：

两种架构分别在原生 runner 构建和扫描，通过后才合并清单并更新版本及 `latest` 标签。发布失败时，可在主分支运行 `Recover unpublished release`：只恢复已合并、通过同提交门禁且尚未创建 Release 的候选标签；不会重写源码标签或已发布版本。

```text
ghcr.io/yuklcool/ai-protocol-platform-backend:v2.0.0
ghcr.io/yuklcool/ai-protocol-platform-frontend:v2.0.0
ghcr.io/yuklcool/ai-protocol-platform-mcp-sandbox:v2.0.0
```

另有精确源码标签 `sha-<完整提交SHA>`。生产使用明确版本，`latest` 不宜作为回滚基线。Compose 中 `BACKEND_IMAGE`、`FRONTEND_IMAGE`、`MCP_SANDBOX_IMAGE` 是镜像仓库名，统一由 `APP_VERSION` 追加标签，不要在这三个变量后重复填写标签。

## 2. 全新安装

```bash
mkdir -p ai-protocol-platform-deploy
cd ai-protocol-platform-deploy
release_version=v2.0.0
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/docker-compose.release.yml" -o docker-compose.release.yml
curl -fL "https://github.com/yuklcool/ai-protocol-platform/releases/download/${release_version}/default.env.selfhost.example" -o .env
chmod 600 .env
openssl rand -base64 48
```

Release 资产名为 `default.env.selfhost.example`，保存为 `.env`；仓库源文件仍为 `.env.selfhost.example`。发布资产已固定 `APP_VERSION=v2.0.0`。

编辑 JWT 密钥、首次管理员、数据库密码及匹配连接串、模型密钥和浏览器源，然后启动：

```bash
docker compose -f docker-compose.release.yml config --quiet
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
docker compose -f docker-compose.release.yml ps
```

默认前端 `http://localhost:3456`，API `http://localhost:1956/docs`，沙箱 `http://localhost:3457/sandbox.html`。登录后继续注册 Provider/模型、配置 Root 及权限，服务启动不代替业务配置。

## 3. 域名和运行时参数

```env
MCP_SANDBOX_PUBLIC_URL=https://mcp.example.com
MCP_SANDBOX_ALLOWED_HOST_ORIGINS=https://ai.example.com
ALLOW_ORIGINS=https://ai.example.com
```

前端与沙箱必须不同源。发布前端启动时替换沙箱 URL 和认证模式，不需要为换域名重建。语言/品牌的任意构建参数不属于通用运行时配置，定制品牌需自建前端镜像。

模型密钥、MCP 密钥、S3 等自定义变量必须显式传入 backend，见[变量传递](../SELFHOST.md#8-环境变量传递)。额外 Compose 文件需在后续所有管理命令中一并使用。

## 4. 数据与 SQL migration

后端镜像已包含 SQL 文件，在账号初始化和 Uvicorn 前执行 `scripts/apply_selfhost_migrations.py`。已执行文件名记录于 `platform_schema_migrations`；重复启动不会重复执行已记录 migration。

不要删除或重命名已发布 SQL 文件。`002_user_owned_reset.sql` 直接清理旧组织目录、专属资源和旧运行状态，不迁移或重分配数据。

固定卷名：

| 卷 | 内容 |
| --- | --- |
| `ai-protocol-platform-postgres-data` | PostgreSQL |
| `ai-protocol-platform-object-data` | `/data/objects` 与 `/data/artifacts` |

多套部署放在同一 Docker 主机时，要显式调整 Compose 中的固定卷名/网络名及端口，否则不能只靠更换目录实现隔离。

## 5. 升级和回滚

升级前记录旧镜像版本/digest，备份数据库、对象卷、配置和签名密钥，先验证当前用户隔离、协议和恢复行为。新模板另存为 `.env.new`，不能覆盖旧 `.env`。

在 `.env` 修改 `APP_VERSION`，执行：

```bash
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

应用回退时恢复旧 `APP_VERSION` 再执行同样命令。若 schema 不兼容，还需恢复匹配的数据库和对象备份。本次改造不提供 ownership journal 或旧组织数据迁移工具。详见[完整升级流程](configuration-guide.md#7-旧部署升级)。

## 6. 发布验收范围

v2.0.0 发布门禁包含同提交的用户归属、模型 Provider、MCP、A2UI、PostgreSQL、镜像构建、漏洞扫描、匿名拉取和全新启动验证。正式 Release 在这些检查通过后创建。

旧数据直接清理的行为由 `002_user_owned_reset.sql` 和真实 PostgreSQL 集成测试验证。发布不会访问或自动重启用户的运行中服务器；目标主机拉取并启动新版本时才执行数据库升级。
