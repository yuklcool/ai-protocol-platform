"use client";
import { useAuth } from "@/contexts/AuthContext";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { PersonalProfileEditor } from "@/components/agent/PersonalProfileEditor";
export default function PersonalSettings() {
  const { user, loading } = useAuth();
  if (loading) return <main className="page-container"><div className="page-body max-w-3xl"><p className="notice notice--info" role="status">加载中…</p></div></main>;
  if (!user) return <SignInRequired />;
  return <main className="page-container"><div className="page-body max-w-3xl"><header className="page-header"><div className="min-w-0"><h1 className="page-header__title">个人 Skill 与信息</h1><p className="page-header__desc">管理你的个人专有 Skill，补充对话中使用的个人信息与偏好。</p></div></header><PersonalProfileEditor uid={user.uid} /></div></main>;
}
