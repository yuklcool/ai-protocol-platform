# 照明技能与安全 SQL

业务查询复用已安装的 `sql-safe-query`：当前对话 → 检索案例/必要 Schema 核验 → 动态生成 SQL → `sql_query_readonly`。没有固定业务 SQL 服务，也不直接连接数据库。六个 `lighting-*` 技能提供业务规则和原型展示契约。

需要原型时，本次动态 SQL 返回唯一一行 `payload`，值符合 `lighting-query/v1`。平台从获授权 MCP 的成功、未截断回包自动生成原有 A2UI/Workbench；普通查询和 Schema 探测不开照明标签页。展示规则不改变用户的时间、范围、状态和分组。结构错误、查询失败和缺测不能转换成零或正常。

部署新后端后，在已授权服务器执行 `apply_skills.py <已部署提交SHA>` 更新已有六技能、Root 路由和绑定。脚本不创建备份、不修改安全 SQL 技能、模型、现有 SQL 服务、OpenViking 或原始 nanobot 技能。旧 `lighting-query` MCP 解绑并停用，随后停止旧适配容器。

本地只编辑。GitHub 专项测试验证原生 SQL MCP 封装、真实 HTTP/一次性 PostgreSQL、六场景契约、失败路径、动作权限和普通查询不误渲染；生产验收通过显式准备的一次性自托管 Runner，用自然语言真实调用技能、动态 SQL 和 A2UI，业务明细不上传 GitHub。证据缺口仍需真实业务数据核实，不据此自动关闭 #152。
