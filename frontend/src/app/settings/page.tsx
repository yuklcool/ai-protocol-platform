"use client";

import Link from "next/link";
import { ArrowUpRight, Activity, Bot, BookOpen, Cpu, ListChecks, Plug, ScrollText, Settings2, UserRound, UsersRound } from "lucide-react";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { useAdminScope } from "@/hooks/useAdminScope";
import { useI18n } from "@/contexts/I18nContext";

const entries = [
  { href: "/settings/personal", zh: "个人信息与偏好", en: "Personal preferences", icon: UserRound, scope: "user", description: ["个人信息、偏好和个人 Skill", "Profile, preferences and personal Skills"] },
  { href: "/agent", zh: "助手配置", en: "Assistant", icon: Bot, scope: "platform", description: ["Root 助手、默认模型与可用能力", "Root assistant, default model and capabilities"] },
  { href: "/admin/model-providers", zh: "模型服务", en: "Model services", icon: Cpu, scope: "platform", description: ["模型供应商、连接与访问配置", "Providers, connections and access"] },
  { href: "/admin/mcp-servers", zh: "MCP 连接", en: "MCP connections", icon: Plug, scope: "admin", description: ["外部工具与服务连接", "External tools and services"] },
  { href: "/admin/knowledge", zh: "知识库", en: "Knowledge", icon: BookOpen, scope: "platform", description: ["检索数据源与知识接入", "Search sources and knowledge access"] },
  { href: "/setup", zh: "配置向导", en: "Setup guide", icon: ListChecks, scope: "platform", description: ["检查部署配置与首次接入", "Deployment configuration and onboarding"] },
  { href: "/admin", zh: "就绪与资源接入", en: "Readiness and resources", icon: Bot, scope: "admin", description: ["能力就绪、资源授权与接入检查", "Capability readiness and resource access"] },
  { href: "/admin/diagnostics", zh: "运行诊断", en: "Diagnostics", icon: Activity, scope: "admin", description: ["定位连接与运行问题", "Investigate connection and runtime issues"] },
  { href: "/admin/analytics", zh: "用量统计", en: "Usage", icon: Activity, scope: "admin", description: ["模型调用与资源使用情况", "Model calls and resource usage"] },
  { href: "/admin/audit", zh: "审计日志", en: "Audit", icon: ScrollText, scope: "admin", description: ["查看已记录的操作", "Review recorded operations"] },
  { href: "/admin/users", zh: "用户与权限", en: "Users and access", icon: UsersRound, scope: "admin", description: ["账号管理与权限分配", "Accounts and permissions"] },
  { href: "/admin/settings", zh: "平台设置", en: "Platform settings", icon: Settings2, scope: "platform", description: ["平台级配置与认证策略", "Platform configuration and authentication"] },
];

function SettingsContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const scope = useAdminScope();
  const visible = entries.filter(item => item.scope === "user" || (item.scope === "platform" ? scope.isPlatform : scope.isAdmin));
  return <main className="page-container mx-auto max-w-5xl">
    <header className="page-header"><div><p className="page-header__eyebrow">{zh ? "你的工作台" : "Your workspace"}</p><h1 className="page-header__title">{zh ? "设置" : "Settings"}</h1><p className="page-header__desc">{zh ? "在这里管理个人偏好、模型和工具连接。" : "Manage preferences, models and tool connections."}</p></div></header>
    {scope.state === "error" && <div role="alert" className="notice notice--danger mb-5"><p>{zh ? "权限加载失败，部分设置暂不可用。" : "Permissions unavailable. Some settings are hidden."}</p><button type="button" className="button-secondary mt-2" onClick={() => void scope.recheck()}>{zh ? "重试" : "Retry"}</button></div>}
    <div className="grid gap-4 sm:grid-cols-2">{visible.map(item => <Link key={item.href} href={item.href} className="glass-panel group flex items-start gap-4 p-5 transition-colors hover:bg-muted/40">
      <item.icon className="mt-1 h-5 w-5 shrink-0 text-primary" aria-hidden="true" /><div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">{zh ? item.zh : item.en}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description[zh ? 0 : 1]}</p></div><ArrowUpRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
    </Link>)}</div>
  </main>;
}

export default function SettingsPage() { return <WorkspaceGate content={SettingsContent} />; }
