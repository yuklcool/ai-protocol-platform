// 从后端读取当前管理权限, 权限组变更不依赖令牌轮换。

"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { fetchWithAuth } from "@/lib/apiClient";

export type AdminScopeKind = "platform" | "tenant" | "none";

/** "loading" until the probe resolves; "error" only for a genuine failure. */
export type AdminScopeState = "loading" | "error" | AdminScopeKind;

export interface AdminScope {
  /** Resolved authority, or loading/error. */
  state: AdminScopeState;
  /** Domains a tenant admin administers (empty for platform — it has all). */
  tenantIds: string[];
  /** True for any admin (platform or tenant) — i.e. show the Admin surface. */
  isAdmin: boolean;
  /** True only for aitana-admin — platform-wide surfaces gate on this. */
  isPlatform: boolean;
  /** 重新查询服务端当前分组与角色。 */
  recheck: () => Promise<void>;
}

/**
 * Resolve the caller's admin scope.
 *
 * @param enabled Defer the request until it's actually needed (the user menu
 *   only probes when opened). Defaults to true.
 */
export function useAdminScope(enabled: boolean = true): AdminScope {
  const { user, loading } = useAuth();
  const [state, setState] = useState<AdminScopeState>("loading");
  const [tenantIds, setTenantIds] = useState<string[]>([]);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setChecked(false);
    setState("loading");
    setTenantIds([]);
  }, [user?.uid, user?.email]);

  const recheck = useCallback(async () => {
    setState("loading");
    setChecked(false);
  }, []);

  useEffect(() => {
    if (!enabled || checked || loading || !user) return;
    let cancelled = false;
    fetchWithAuth("/api/proxy/api/admin/whoami")
      .then(async (r) => {
        if (cancelled) return;
        if (!r.ok) {
          // whoami answers 200 for every authenticated caller, so a non-ok
          // here is a real failure (network, auth, backend) — surface it as
          // "error", never silently as "not an admin".
          setState("error");
          setChecked(true);
          return;
        }
        const body = (await r.json()) as {
          scope?: string;
          tenantIds?: string[];
        };
        const scope =
          body.scope === "platform" || body.scope === "tenant"
            ? body.scope
            : "none";
        setState(scope);
        setTenantIds(Array.isArray(body.tenantIds) ? body.tenantIds : []);
        setChecked(true);
      })
      .catch(() => {
        if (!cancelled) {
          setState("error");
          setChecked(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, checked, loading, user]);

  return {
    state,
    tenantIds,
    isAdmin: state === "platform" || state === "tenant",
    isPlatform: state === "platform",
    recheck,
  };
}
