"use client";

import Link from "next/link";
import { useState } from "react";
import { Activity, ArrowUpRight, RotateCw } from "lucide-react";
import { AgentReadiness } from "@/components/admin/AgentReadiness";
import { BackendHealthBadge } from "@/components/BackendHealthBadge";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { useAdminScope } from "@/hooks/useAdminScope";
import { useI18n } from "@/contexts/I18nContext";

function DiagnosticsContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const scope = useAdminScope();
  const [revision, setRevision] = useState(0);
  if (scope.state === "loading") return <main className="page-container"><p role="status">{zh ? "正在核对权限…" : "Checking access…"}</p></main>;
  if (!scope.isAdmin) return <main className="page-container"><h1>{zh ? "运行诊断" : "Diagnostics"}</h1><p role="alert" className="notice notice--warning">{zh ? "需要管理员权限。" : "Administrator access required."}</p></main>;
  return <main className="page-container mx-auto max-w-6xl"><header className="page-header"><div><p className="page-header__eyebrow">{zh ? "运行与连接" : "Runtime & connections"}</p><h1 className="page-header__title">{zh ? "运行诊断" : "Diagnostics"}</h1><p className="page-header__desc">{zh ? "检查服务可达性、模型验证记录与工具连接。" : "Inspect service reachability, model checks and tool connections."}</p></div><button type="button" className="button-secondary" onClick={() => setRevision(value => value + 1)}><RotateCw className="h-4 w-4" />{zh ? "刷新检查" : "Refresh checks"}</button></header><section className="glass-panel mb-5 flex flex-wrap items-center justify-between gap-4 p-5"><div className="flex items-center gap-3"><Activity className="h-5 w-5 text-primary" /><div><h2>{zh ? "后端服务" : "Backend service"}</h2><p className="text-xs text-muted-foreground">{zh ? "健康接口可达性；不代表模型或工具验证通过。" : "Health endpoint reachability, independent of model and tool checks."}</p></div></div><BackendHealthBadge key={revision} /></section><AgentReadiness key={`readiness-${revision}`} /><div className="grid gap-4 sm:grid-cols-2">{[{ href: "/admin/model-providers", title: zh ? "模型诊断" : "Model diagnostics", desc: zh ? "运行文本生成与原生工具调用测试。" : "Run completion and native tool-call checks." }, { href: "/admin/mcp-servers", title: zh ? "MCP 连接诊断" : "MCP connection diagnostics", desc: zh ? "检查健康状态、发现工具并核对授权。" : "Check health, discover tools and review access." }].map(item => <Link key={item.href} href={item.href} className="glass-panel feature-card p-5"><div className="flex items-center justify-between"><h2>{item.title}</h2><ArrowUpRight className="h-4 w-4 text-primary" /></div><p className="mt-2 text-sm text-muted-foreground">{item.desc}</p></Link>)}</div></main>;
}

export default function DiagnosticsPage() { return <WorkspaceGate content={DiagnosticsContent} />; }
