"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { fetchWithAuth } from "@/lib/apiClient";
export type AdminScopeKind = "platform" | "none";
export type AdminScopeState = "loading" | "error" | AdminScopeKind;
export interface AdminScope { state: AdminScopeState; isAdmin: boolean; isPlatform: boolean; recheck: () => Promise<void> }
export function useAdminScope(enabled = true): AdminScope {
  const { user, loading } = useAuth();
  const uid = user?.uid;
  const email = user?.email;
  const [state, setState] = useState<AdminScopeState>("loading");
  const [revision, setRevision] = useState(0);
  const recheck = useCallback(async () => setRevision(value => value + 1), []);
  useEffect(() => {
    setState("loading");
    if (!enabled || loading || !uid) return;
    let cancelled = false;
    fetchWithAuth("/api/proxy/api/admin/whoami").then(async response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.json();
      if (!cancelled) setState(body.scope === "platform" ? "platform" : "none");
    }).catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, [enabled, loading, uid, email, revision]);
  return { state, isAdmin: state === "platform", isPlatform: state === "platform", recheck };
}
