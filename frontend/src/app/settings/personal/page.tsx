"use client";
import { useAuth } from "@/contexts/AuthContext";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { PersonalProfileEditor } from "@/components/agent/PersonalProfileEditor";
export default function PersonalSettings() {
  const { user, loading } = useAuth();
  if (loading) return <main className="page-container p-8">加载中…</main>;
  if (!user) return <SignInRequired />;
  return <main className="page-container mx-auto max-w-3xl space-y-6 p-8"><h1 className="text-2xl font-semibold">个人 Skill 与信息</h1><PersonalProfileEditor uid={user.uid} /></main>;
}
