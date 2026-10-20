# 项目交接状态

更新时间：2026-10-20。仓库：`yuklcool/ai-protocol-platform`。

## 当前基线

当前清理基于 main `0a52c4e85f783cf263c2fdc8180fa1941124cef6`。该提交的 19 个检查通过，包含 PostgreSQL、认证、模型接入、浏览器、MCP/MCP Apps、A2UI 与真实 Provider 门禁。证据见 [Actions](https://github.com/yuklcool/ai-protocol-platform/actions/runs/39276219948)。后续提交必须检查自己的 CI。

- #120/#121 权限边界由 PR #123 合并。
- #119 附件上传分析由 PR #125 实现，#118 模型接入由 PR #126 实现；PR #128 完成浅色界面及组合验收。
- #118/#119 已按用户指定 `https://sub2api.yukl.qzz.io`、`gpt-6-luna` 完成 15 项定向验收并关闭；真实模型调用、附件随机标记/计算/来源/续聊及跨租户拒绝通过，具体测试范围见对应 Issue。
- 密钥只来自运行环境，交接文档不保存实际值。

## 发布与目标部署

正式发布镜像仍为 [v1.1.1](https://github.com/yuklcool/ai-protocol-platform/releases/tag/v1.1.1)，基线 `29688543e0b4c1749210a8be90b0c94a207ca87e`。后续 Root/Skill 简化、权限、附件、模型页和界面修改已经进入源码，但不能据此声称旧发布镜像包含这些修改。

[Issue #9](https://github.com/yuklcool/ai-protocol-platform/issues/9) 的目标安装历史 ownership、Session/Memory 迁移、备份恢复与回滚尚未完成。默认自托管的认证与数据持久化通过，不代表目标生产已升级。冻结部署快照不自动跟随 main，也不重写。

## 待办入口

| Issue | 范围 |
| --- | --- |
| [#9](https://github.com/yuklcool/ai-protocol-platform/issues/9) | 目标安装历史迁移与回滚 |
| [#15](https://github.com/yuklcool/ai-protocol-platform/issues/15) | 总 Roadmap；具体状态以子 Issue 为准 |
| [#124](https://github.com/yuklcool/ai-protocol-platform/issues/124) | 沙箱与前端部署整合，保持浏览器源隔离 |
| [#127](https://github.com/yuklcool/ai-protocol-platform/issues/127) | Root Studio 配置版本、评测和可观测性 |
| [#129](https://github.com/yuklcool/ai-protocol-platform/issues/129) | 共享 A2UI rendering Skill，复用现有 SDK/授权链路 |

## 当前文档

- [完整配置流程](docs/configuration-guide.md)：统一操作入口。
- [自托管与运维](SELFHOST.md)：认证、持久化、网络、备份及开发。
- [模块边界](docs/module-simplification.md)：Root 与 Skill 的最终职责。
- [历史设计索引](docs/archive/design/README.md)：上游背景，不作为当前待办或部署指令。

详细提交和历史验收在 Git 历史、PR 和 Actions 中保留，不在本文件重复维护旧的完整提交清单。
