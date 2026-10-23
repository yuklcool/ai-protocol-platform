"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Check, ChevronRight, RotateCw } from "lucide-react";
import { WorkspaceGate } from "@/components/workspace/WorkspaceGate";
import { AgentReadiness } from "@/components/admin/AgentReadiness";
import { useAdminScope } from "@/hooks/useAdminScope";
import { useI18n } from "@/contexts/I18nContext";

const Models = dynamic(() => import("@/app/admin/model-providers/page"), { loading: () => <p role="status">Loading…</p> });
const Agent = dynamic(() => import("@/app/agent/page"), { loading: () => <p role="status">Loading…</p> });
const Mcp = dynamic(() => import("@/app/admin/mcp-servers/page"), { loading: () => <p role="status">Loading…</p> });
const steps = [["模型接入", "Model connection"], ["Agent 配置", "Agent configuration"], ["连接工具（可选）", "Connect tools (optional)"], ["验证配置", "Verify setup"]];

function SetupContent() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const scope = useAdminScope();
  const [step, setStep] = useState(0);
  const [revision, setRevision] = useState(0);
  const [verified, setVerified] = useState(false);
  if (scope.state === "loading") return <main className="page-container"><p role="status">{zh ? "正在核对权限…" : "Checking access…"}</p></main>;
  if (!scope.isPlatform) return <main className="page-container"><h1>{zh ? "配置向导" : "Setup guide"}</h1><p role="alert" className="notice notice--warning mt-4">{zh ? "此向导需要平台管理员权限。" : "Platform administrator access is required."}</p></main>;
  return <div className="page-container mx-auto max-w-6xl">
    <header className="page-header"><div><p className="page-header__eyebrow">{zh ? "开始使用" : "Getting started"}</p><h1 className="page-header__title">{zh ? "配置向导" : "Setup guide"}</h1><p className="page-header__desc">{zh ? "接入模型、保存公共能力，并用真实测试检查就绪状态。" : "Connect a model, save shared capabilities and verify readiness with real checks."}</p></div><Link href="/admin" className="button-ghost">{zh ? "稍后继续" : "Continue later"}</Link></header>
    <nav className="setup-steps" aria-label={zh ? "配置步骤" : "Setup steps"}>{steps.map((labels, index) => <button key={index} type="button" aria-current={step === index ? "step" : undefined} onClick={() => { setStep(index); setVerified(false); }}><span className="setup-step-number">{index + 1}</span><span>{labels[zh ? 0 : 1]}</span></button>)}</nav>
    <div className="setup-content mt-5">{step === 0 ? <Models /> : step === 1 ? <Agent /> : step === 2 ? <Mcp /> : <main><div className="mb-4 flex items-center justify-between gap-3"><h2>{zh ? "检查已保存配置" : "Check saved configuration"}</h2><button type="button" className="button-secondary" onClick={() => { setVerified(false); setRevision(value => value + 1); }}><RotateCw className="h-4 w-4" />{zh ? "重新读取" : "Refresh"}</button></div><AgentReadiness key={revision} onVerified={setVerified} />{verified && <p role="status" className="notice notice--success"><Check className="h-4 w-4" />{zh ? "模型配置一致，文本与工具调用测试已通过。现在可以在对话中验证任务；用户授权和外部工具仍需按实际任务核对。" : "Model configuration is consistent and both model checks passed. Validate a task in chat, including user access and external tools."}</p>}</main>}</div>
    <footer className="setup-footer mt-6 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted-foreground">{zh ? "请先在当前表单保存修改，再进入下一步。步骤编号不代表验证通过。" : "Save the current form before moving on. Step numbers do not indicate verification."}</p><div className="flex gap-2">{step > 0 && <button type="button" className="button-secondary" onClick={() => setStep(value => value - 1)}>{zh ? "上一步" : "Back"}</button>}{step < 3 ? <button type="button" className="button-primary" onClick={() => setStep(value => value + 1)}>{zh ? "下一步" : "Next"}<ChevronRight className="h-4 w-4" /></button> : <Link href="/chat/root-agent" className="button-primary">{zh ? "前往对话验证" : "Validate in chat"}<ChevronRight className="h-4 w-4" /></Link>}</div></footer>
  </div>;
}

export default function SetupPage() { return <WorkspaceGate content={SetupContent} />; }
