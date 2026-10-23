"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useLandingTarget } from "@/hooks/useLandingTarget";

/** 未登录保留公共首页，登录后直接进入 AI 任务对话。 */
export function HomeGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const { locale } = useI18n();
  const target = useLandingTarget(!loading && !!user);

  const href = target.kind === "chat" ? target.href : null;
  useEffect(() => {
    if (!loading && user && href) router.replace(href);
  }, [loading, user, href, router]);

  if (loading || !user) return <>{children}</>;

  // 跳转期间不显示宣传页。
  return (
    <div
      data-testid="home-gate-redirecting"
      className="flex min-h-screen items-center justify-center text-sm text-muted-foreground"
      role="status"
      aria-live="polite"
    >
      <span className="inline-flex items-center gap-2">
        <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.25" />
          <path d="M12 2 a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" fill="none" />
        </svg>
        {locale.startsWith("zh") ? "正在进入 AI 任务对话…" : "Opening your AI conversation…"}
      </span>
    </div>
  );
}
