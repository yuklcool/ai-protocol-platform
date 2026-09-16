// EffectiveAccessPanel — "what your users actually see" (v6.16.0 Phase 2).
// Backend-authored verdict/reason strings remain verbatim; this component only
// localizes its own explanatory and control copy.

"use client";

import { useCallback, useState } from "react";

import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import {
  translateTenantAdmin,
  type TenantAdminTranslationKey,
} from "@/lib/i18n/tenantAdmin";

interface SkillRow {
  skillId: string;
  slug: string;
  label: string;
  visible: boolean;
  reason: string;
  accessAllowed: boolean;
  tenantAllowed: boolean;
  adminBypass: boolean;
}

interface VisibilityPlane {
  enabledSkills: string[] | null;
  visibleCount: number;
  totalCount: number;
  hiddenByTenantFilter: string[];
  skills: SkillRow[];
}

interface CheckResponse {
  email: string;
  domain: string;
  userFound?: boolean;
  user_found?: boolean;
  skillVisibility?: VisibilityPlane | null;
}

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; email: string; userFound: boolean; plane: VisibilityPlane };

type TenantT = (key: TenantAdminTranslationKey, params?: Record<string, string | number>) => string;

export function EffectiveAccessPanel({ domain }: { domain: string }) {
  const { locale } = useI18n();
  const t: TenantT = (key, params = {}) => translateTenantAdmin(locale, key, params);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  const run = useCallback(
    async (target: string) => {
      const addr = target.trim();
      if (!addr) return;
      setState({ kind: "loading" });
      try {
        const r = await fetchWithAuth("/api/proxy/api/admin/access/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: addr, includeSkills: true }),
        });
        if (!r.ok) {
          const detail =
            r.status === 403
              ? t("access.outOfScope", { email: addr, domain })
              : t("access.checkFailed", { status: r.status });
          setState({ kind: "error", message: detail });
          return;
        }
        const body = (await r.json()) as CheckResponse;
        if (!body.skillVisibility) {
          setState({ kind: "error", message: t("access.noVisibility") });
          return;
        }
        setState({
          kind: "ready",
          email: body.email || addr,
          userFound: Boolean(body.userFound ?? body.user_found),
          plane: body.skillVisibility,
        });
      } catch {
        setState({ kind: "error", message: t("access.connectionFailed") });
      }
    },
    [domain, locale],
  );

  return (
    <div className="rounded-lg border border-border p-4">
      <h3 className="text-sm font-semibold text-foreground">{t("access.title")}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{t("access.description")}</p>

      <form
        className="mt-3 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(email);
        }}
      >
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={`someone@${domain}`}
          aria-label={t("access.emailAria")}
          className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={!email.trim() || state.kind === "loading"}
          className="rounded border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
        >
          {state.kind === "loading" ? t("access.checking") : t("access.check")}
        </button>
      </form>

      {state.kind === "error" && (
        <p className="mt-3 rounded border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {state.message}
        </p>
      )}

      {state.kind === "ready" && <Result state={state} t={t} />}
    </div>
  );
}

function Result({ state, t }: { state: Extract<State, { kind: "ready" }>; t: TenantT }) {
  const { plane, email, userFound } = state;
  const hidden = plane.hiddenByTenantFilter;

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
        <span className="font-medium text-foreground">
          {t("access.visibleSummary", {
            visible: plane.visibleCount,
            total: plane.totalCount,
            email,
          })}
        </span>
        {!userFound && (
          <span className="text-amber-600 dark:text-amber-500">{t("access.notSignedIn")}</span>
        )}
      </div>

      {plane.enabledSkills === null ? (
        <p className="text-xs text-muted-foreground">{t("access.noFilter")}</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t("access.filterActive")}{" "}
          <code className="text-[11px]">{plane.enabledSkills.join(", ") || t("access.emptyFilter")}</code>
        </p>
      )}

      {hidden.length > 0 && (
        <p className="rounded border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-500">
          {t(hidden.length === 1 ? "access.hiddenOne" : "access.hiddenMany", {
            count: hidden.length,
            skills: hidden.join(", "),
          })}
        </p>
      )}

      {plane.skills.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("access.noSkills")}</p>
      ) : (
        <ul className="divide-y divide-border rounded border border-border">
          {plane.skills.map((s) => (
            <li key={s.skillId || s.slug} className="flex items-start gap-3 px-3 py-2">
              <span
                aria-hidden
                className={
                  "mt-1 h-2 w-2 shrink-0 rounded-full " +
                  (s.visible ? "bg-emerald-500" : "bg-muted-foreground/40")
                }
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span
                    className={
                      "text-sm " +
                      (s.visible ? "text-foreground" : "text-muted-foreground line-through")
                    }
                  >
                    {s.label || s.slug}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {s.visible ? t("access.visible") : t("access.hidden")}
                  </span>
                  {s.adminBypass && !s.tenantAllowed && (
                    <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-500">
                      {t("access.adminBypass")}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{s.reason}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
