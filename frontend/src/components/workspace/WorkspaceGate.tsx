"use client";

import type { ComponentType } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { SignInRequired } from "@/components/chat/SignInRequired";

export function WorkspaceGate({ content: Content }: { content: ComponentType }) {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  if (loading) {
    return <main className="flex min-h-[100dvh] items-center justify-center text-muted-foreground" role="status">{locale.startsWith("zh") ? "正在确认登录状态…" : "Checking sign-in…"}</main>;
  }
  if (!user) return <SignInRequired />;
  return <Content key={user.uid} />;
}
