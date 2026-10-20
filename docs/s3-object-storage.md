# S3 兼容对象存储

默认使用本地文件卷。S3 是可选适配，不会自动启动 MinIO 或任何 S3 服务，也不会自动搬迁已有对象。Artifact 存储独立配置，启用对象存储 S3 不代表 Artifact 同时改用 S3。

## 1. 配置参数

将以下实际值放入 `.env`：

```env
OBJECT_STORAGE_BACKEND=s3
OBJECT_STORAGE_S3_BUCKET=platform-objects
OBJECT_STORAGE_S3_ENDPOINT=https://s3.example.com
OBJECT_STORAGE_S3_REGION=us-east-1
OBJECT_STORAGE_S3_ACCESS_KEY=替换为访问密钥
OBJECT_STORAGE_S3_SECRET_KEY=替换为私有密钥
OBJECT_STORAGE_S3_SESSION_TOKEN=
OBJECT_STORAGE_S3_ADDRESSING_STYLE=path
```

AWS S3 可省略自定义 endpoint，使用 boto3 凭证链/IAM 时不填显式密钥。R2 通常用账户 endpoint 与 `REGION=auto`；寻址方式支持 `auto`、`path`、`virtual`，按服务实际配置填写。

## 2. 显式传入 backend

默认 Compose 未逐项传递 S3 参数；只编辑 `.env` 不够。创建 `docker-compose.storage.yml`：

```yaml
services:
  backend:
    environment:
      OBJECT_STORAGE_BACKEND: s3
      OBJECT_STORAGE_S3_BUCKET: "${OBJECT_STORAGE_S3_BUCKET:?请填写bucket}"
      OBJECT_STORAGE_S3_ENDPOINT: "${OBJECT_STORAGE_S3_ENDPOINT:-}"
      OBJECT_STORAGE_S3_REGION: "${OBJECT_STORAGE_S3_REGION:-us-east-1}"
      OBJECT_STORAGE_S3_ACCESS_KEY: "${OBJECT_STORAGE_S3_ACCESS_KEY:-}"
      OBJECT_STORAGE_S3_SECRET_KEY: "${OBJECT_STORAGE_S3_SECRET_KEY:-}"
      OBJECT_STORAGE_S3_SESSION_TOKEN: "${OBJECT_STORAGE_S3_SESSION_TOKEN:-}"
      OBJECT_STORAGE_S3_ADDRESSING_STYLE: "${OBJECT_STORAGE_S3_ADDRESSING_STYLE:-auto}"
```

```bash
docker compose -f docker-compose.release.yml -f docker-compose.storage.yml config --quiet
docker compose -f docker-compose.release.yml -f docker-compose.storage.yml up -d
```

源码部署将第一个文件改为 `docker-compose.yml`；已有额外配置时带齐所有 `-f`，后续管理保持一致。

## 3. 用户与传输

业务接口以 `(user_id, key)` 访问，对象实际前缀为 `users/<user_id>/<key>`。适配层拒绝 `..`、绝对路径、反斜杠、空路径段及带路径分隔符的 user ID。

`put_fileobj()` 使用托管分片上传，必要时将分片提升到 S3 最小 5 MiB；`iter_bytes()` 增量读取并关闭响应，内存有界。也提供 `put_bytes()`、`get_bytes()`、`exists()`、`delete()`、`list_objects()`。

远程存储支持预签名上传/下载，先加用户前缀再签名，有效期 1 秒至 7 天。上传若签入 `content_type`，实际 `Content-Type` 必须相同。本地存储不生成预签名 URL，继续使用认证上传/下载接口。

## 4. 切换和验收

先备份并逐对象核对旧 metadata、用户和物理路径，制定复制与回滚方案。验证上传、预览、下载、删除、重启持久化、跨用户拒绝及预签名范围。S3 对象备份需与 PostgreSQL 元数据保持可恢复的一致关系。
