# sql-safe-query Skill 运行适配

将 nanobot 的安全查询 Skill 接入平台已有的 Root Skill 和 HTTP MCP 机制。
原有检索算法、样例、模板和 Schema 均由部署目录提供，不放入公开仓库。
适配器仅提供 `sql_retrieve_examples(question, top_k=5)`，不提供 SQL 执行、文件写入或命令执行。
SQL 继续使用已有的 `sql_query_readonly`；动态案例继续使用已有的 OpenViking。

## 部署文件

在平台部署目录保留以下结构：

```text
skills/sql-safe-query/                  # 原 Skill 完整副本，活跃文档适配平台
  SKILL.md
  scripts/retrieve_examples.py         # 保持原始脚本
  data/{training_data,text2sql_index,sql_templates}.json
infrastructure/sql-safe-query-mcp/
  serve.py
  requirements.txt
  compose.yml
  dependencies/                       # 项目内依赖，由下面的命令安装
```

源目录的完整归档和文件 SHA256 清单应放入部署备份目录。历史 `.bak`、
`_bak.json` 和 `__pycache__` 保留在原始归档中，不作为活跃检索数据。

本适配器复用平台 v2.4.3 后端镜像里的 Python 和 MCP 1.30.0，避免构建新镜像。
在部署服务器项目根目录执行：

```sh
mkdir -p infrastructure/sql-safe-query-mcp/dependencies
docker run --rm --user 0:0 \
  -v "$PWD/infrastructure/sql-safe-query-mcp:/adapter" \
  ghcr.io/yuklcool/ai-protocol-platform-backend:v2.4.3 \
  uv pip install --python /app/.venv/bin/python \
  --target /adapter/dependencies -r /adapter/requirements.txt
docker compose -f infrastructure/sql-safe-query-mcp/compose.yml up -d
```

确保活跃 Skill 和依赖文件在容器内对 UID 65534 可读，目录可遍历。
项目外层目录和备份可保持仅管理员可读。
服务不发布宿主机端口，代码、Skill 和依赖只读挂载，仅 `/tmp` 可写。
不要将该服务直接公开到公网；它使用平台的授权 MCP 入口供已授权用户调用。

在管理界面注册 MCP `sql-safe-query-examples`：

- 地址：`http://sql-safe-query-mcp:8011/mcp`
- 传输：`streamable-http`
- 绑定到需要此能力的 Root Agent。

通过 Skill API 创建私有 `sql-safe-query` 并将 Skill ID 绑定到 Root。
Skill instructions 使用适配后的 `SKILL.md`，references 只放小型运行说明。
不要将大体积 JSON 或脚本放入 Skill references/assets：`load_skill` 会全量返回它们。

适配后的规则应先 `find/read` 动态已验证案例，无完全匹配时调用
`sql_retrieve_examples`，按需核验 Schema 后通过 `sql_query_readonly` 执行。
不能声称平台有 nanobot 的 `exec`、工作区文件读取或本地导出能力。

## 验证与回退

适配器的真实 HTTP MCP 合约和输入边界在 GitHub Actions 验证，使用合成数据。
服务器验收还需确认原始文件校验值、六类业务问题的检索一致性、
Skill 有效权限及真实 Agent 加载和查询。验收会话用完删除；健康检查不入案例库。

如需撤回，从 Root 解绑本次 Skill 和 MCP，再停止这个独立 Compose 服务。
恢复迁移前的平台配置备份即可；不修改 nanobot 源目录、SQL 服务或既有案例。
