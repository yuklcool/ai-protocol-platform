"use client";

import { ArrowUpRight, Check, FileText, Layers3 } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { SignInButton } from "@/components/SignInButton";

export function OneHeroVisual() {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  return <section className="landing-access glass-panel overflow-hidden" aria-label={zh ? "登录工作区" : "Sign in to your workspace"}>
    <div className="border-b p-6 sm:p-8"><div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Layers3 className="h-6 w-6" /></div><h2 className="text-2xl font-semibold">{zh ? "你的 AI 工作空间" : "Your AI workspace"}</h2><p className="mb-6 mt-3 text-sm text-muted-foreground">{zh ? "登录后开始对话，随时讨论、使用资料和保存成果。" : "Sign in to chat, use documents and save results."}</p><SignInButton /></div>
    <div className="space-y-4 bg-[var(--canvas)] p-6 sm:p-8"><div className="flex items-center justify-between text-xs text-muted-foreground"><span>{zh ? "从目标到成果" : "From goal to result"}</span><span className="badge">{zh ? "界面示例" : "Interface preview"}</span></div>
      <div className="rounded-2xl border bg-white p-4"><p className="mb-4 text-sm font-semibold">{zh ? "整理资料，生成一份清晰的报告" : "Turn your research into a clear report"}</p><div className="space-y-3">{(zh ? ["确认任务目标", "整理并核对资料", "生成可编辑的报告"] : ["Confirm the goal", "Review source material", "Create an editable report"]).map(label => <div key={label} className="flex items-center gap-3 text-sm"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary"><Check className="h-3 w-3" /></span><span>{label}</span></div>)}</div></div>
      <div className="flex items-center gap-3 rounded-2xl border bg-white p-4"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><FileText className="h-5 w-5" /></span><div className="flex-1"><p className="text-sm font-medium">{zh ? "任务报告" : "Task report"}</p><p className="text-xs text-muted-foreground">{zh ? "预览 · 编辑 · 保存 · 导出" : "Preview · Edit · Save · Export"}</p></div><ArrowUpRight className="h-4 w-4 text-muted-foreground" /></div>
      <p className="text-xs text-muted-foreground">{zh ? "此处为静态示例；实际结果由已配置的模型与授权工具生成。" : "Static preview. Actual results depend on configured models and authorized tools."}</p>
    </div>
  </section>;
}
