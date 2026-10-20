# 用户调用归属

认证后通过 `observability.user_context.set_user_context` 绑定可信 UID。`UserAttributeSpanProcessor` 将 `user.id` 与认证方式附加到当前调用 Span；不附加原始邮箱。客户端附加信息不能覆盖 `user.*` 或 `resource.*` 身份字段。

管理员跨用户读取资源时，先检查管理权限与资源所有者，再使用 `authorized_resource_user` 暂时选择资源存储范围；调用者身份保持不变。上下文在退出时恢复。
