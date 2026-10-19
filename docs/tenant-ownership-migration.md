# 历史租户归属迁移与回滚

本手册将旧 domain ownership 迁移为稳定 `tenant_id`，所有映射必须来自权威数据。完整升级顺序见[配置流程](configuration-guide.md#12-已有部署升级迁移与回滚)。

## 1. 工具覆盖范围

`backend/scripts/migrate_tenants.py` 处理可信 metadata 关系：

- `clients/{domain}` 到 `tenants/{tenant_id}`，以及 `tenant_domains` 映射。
- 尚无显式归属的本地 `auth_users.tenantId` 和租户管理员标签。
- 相容的旧域工具规则到 `tool_permissions/tenant:<tenant_id>`。
- 可精确关联本地账号的用户工具权限归属。
- 目标资源归属明确的历史管理审计。
- 可明确关联可信本地账号的旧用户 Skill 归属；同 UID 跨租户歧义时不自动补齐。

不会通过 `actorEmail`、任意邮箱或命名启发式推断归属。**该工具不执行完整 ADK Session/Memory namespace 搬迁，也不自动迁移所有文件字节或外部 IdP。**

## 2. 执行前准备

备份数据库和文件/Artifact 卷、配置与签名密钥，在隔离副本验证恢复。确认命令连接的是预期副本/目标数据库，不要因在源码目录运行就默认认为使用了生产环境。

确定 domain→tenant 映射，使用稳定、不随邮箱改变的 ID。生产必须使用 `--require-explicit`，未映射域应失败，而不是自动当作新租户。

以下冲突拒绝自动处理：合并域配置不同、工具规则不一致、已有租户/域映射冲突、用户工具规则与权威账号归属不符。已有显式 `auth_users.tenantId` 不被邮箱域覆盖。无法证明归属的旧记录继续仅平台管理员可管理。

## 3. 执行 dry-run

在已正确配置依赖和数据库环境的源码目录：

```bash
cd backend
uv run python scripts/migrate_tenants.py \
  --map acme.com=tenant-acme \
  --map acme-energy.example=tenant-acme \
  --require-explicit
```

默认不写数据，也不创建 journal。逐项人工复核输出及歧义，不要为了通过而扩大归属。

镜像部署也可在对应 backend 容器内运行，例如先在副本中：

```bash
docker compose -f docker-compose.release.yml exec backend \
  uv run python scripts/migrate_tenants.py \
  --map acme.com=tenant-acme --require-explicit
```

有额外 Compose 文件时需带齐相同 `-f` 参数。

## 4. apply 与验证

审核通过且已有可恢复备份后，在相同命令末尾增加 `--apply`。保存输出的 migration run id。工具创建 `tenant_migration_runs/{run_id}` 和 `tenant_migration_operations/{run_id}:{sequence}`。

journal 对旧记录只保存修改字段的前后值，不复制完整 `auth_users` 或 `passwordHash`。

逐项验证：

1. 域映射、账号登录的 stable tenant、管理员标签符合审核。
2. 租户工具规则与旧规则一致，用户规则仍受租户策略上限约束。
3. A 无法读取/使用 B 的规则，审计查询及计数只返回授权范围。
4. 歧义账号、Skill 和审计未被误分配。

保留旧 `clients/{domain}` 和 domain 工具记录作为兼容/回滚输入，不在本次迁移中删除。

## 5. journal 回滚

```bash
cd backend
migration_run_id=替换为实际run-id
uv run python scripts/migrate_tenants.py --rollback "$migration_run_id"
```

回滚先完整检查 drift：任何已迁移字段不再等于记录的 after-state 时，在修改任何操作前停止，保护后续业务修改。

无 drift 时删除迁移新建记录、恢复旧记录中被修改字段，保留无关字段及当前密码哈希。journal 保留并标为 `rolled_back`。回滚实测必须包含无 drift 恢复和有 drift 拒绝两种情况。

## 6. Session、Memory、文件及外部身份

| 数据 | 额外要求 |
| --- | --- |
| ADK Session | 按权威索引审核事件、状态和 app/user state 到可信租户 namespace 的迁移；验证可续聊 |
| Memory | 按 tenant/app/UID 迁移，验证原租户可召回、同 UID 其他租户不可召回 |
| 文件/Artifact | 核对 metadata 归属和物理对象路径，验证预览、下载与越权拒绝 |
| Firebase/OIDC | 在权威身份源和显式 subject mapping 中处理，不能用本地猜测记录代替 |

namespace 变更需单独的可审核计划、执行记录及撤销方案。切换旧镜像不自动恢复旧 namespace；不兼容 schema 需恢复匹配数据库/对象备份。

## 7. Issue #9 关闭条件

目标真实数据完成 dry-run → 人工审核 → apply → verify，并实测 journal/namespace/整体恢复路径；迁移后的真实 A/B 验收覆盖 Session/Memory、文件、私有 Skill、MCP、审计、模型、工具与额度。

发布和新环境证据已存在，不能替代目标数据验收。保留 [Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 的现场记录，达到关闭标准后才考虑移除旧兼容路径。
