// Tenant-Admin — manage client-org (domain) config in the app instead of by hand.

"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { translateTenantAdmin } from "@/lib/i18n/tenantAdmin";
import { EffectiveAccessPanel } from "@/components/admin/EffectiveAccessPanel";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { TenantEditor } from "@/components/admin/TenantEditor";
import { TenantOnboardWizard } from "@/components/admin/TenantOnboardWizard";
import type { ClientConfig, SkillOption, TenantValidation } from "@/components/admin/tenantAdmin";
import { HealthBadge, type HealthState, ReachDot } from "@/components/admin/tenantHealth";

interface SkillLite {
  slug?: string | null;
  displayName?: string;
  name?: string;
}

// Technical owner id used by the existing Skill API. This is not display branding.
const PLATFORM_OWNER_UID = "aitana-platform";

type Status =
  | { kind: "loading" }
  | { kind: "forbidden" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

type Panel =
  | { mode: "none" }
  | { mode: "new" }
  | { mode: "edit"; tenant: ClientConfig }
  | { mode: "access"; tenant: ClientConfig };

export default function TenantAdminPage() {
  const { user, loading: authLoading } = useAuth();
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translateTenantAdmin>[1],
    params: Record<string, string | number> = {},
  ) => translateTenantAdmin(locale, key, params);
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [tenants, setTenants] = useState<ClientConfig[]>([]);
  const [skills, setSkills] = useState<SkillOption[]>([]);
  const [skillNotice, setSkillNotice] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>({ mode: "none" });
  const [notice, setNotice] = useState<string | null>(null);
  const [health, setHealth] = useState<Record<string, HealthState>>({});

  const loadHealth = useCallback(async (domains: string[]) => {
    setHealth(Object.fromEntries(domains.map((d) => [d, { kind: "loading" } as HealthState])));
    await Promise.all(
      domains.map(async (d) => {
        try {
          const r = await fetchWithAuth(
            `/api/proxy/api/admin/tenants/${encodeURIComponent(d)}/validate`,
          );
          if (!r.ok) {
            setHealth((h) => ({ ...h, [d]: { kind: "error" } }));
            return;
          }
          const validation = (await r.json()) as TenantValidation;
          setHealth((h) => ({ ...h, [d]: { kind: "ready", validation } }));
        } catch {
          setHealth((h) => ({ ...h, [d]: { kind: "error" } }));
        }
      }),
    );
  }, []);

  const loadTenants = useCallback(async () => {
    setStatus({ kind: "loading" });
    try {
      const r = await fetchWithAuth("/api/proxy/api/admin/clients");
      if (r.status === 403) return setStatus({ kind: "forbidden" });
      if (!r.ok) return setStatus({ kind: "error", message: `HTTP ${r.status}` });
      const data: ClientConfig[] = await r.json();
      data.sort((a, b) => a.domain.localeCompare(b.domain));
      setTenants(data);
      setStatus({ kind: "ready" });
      void loadHealth(data.map((item) => item.domain));
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : translateTenantAdmin(locale, "page.loadFailed"),
      });
    }
  }, [loadHealth, locale]);

  const loadSkills = useCallback(async () => {
    setSkillNotice(null);
    try {
      const [ownRes, platformRes] = await Promise.all([
        fetchWithAuth("/api/proxy/api/skills"),
        fetchWithAuth(`/api/proxy/api/skills?ownerId=${encodeURIComponent(PLATFORM_OWNER_UID)}`),
      ]);
      if (!ownRes.ok && !platformRes.ok) {
        setSkillNotice(translateTenantAdmin(locale, "page.skillsUnavailable"));
        return;
      }
      const own: SkillLite[] = ownRes.ok ? await ownRes.json() : [];
      const platform: SkillLite[] = platformRes.ok ? await platformRes.json() : [];
      const bySlug = new Map<string, SkillOption>();
      for (const skill of [...own, ...platform]) {
        if (!skill.slug) continue;
        if (!bySlug.has(skill.slug)) {
          bySlug.set(skill.slug, {
            slug: skill.slug,
            displayName: skill.displayName || skill.name || skill.slug,
          });
        }
      }
      setSkills([...bySlug.values()].sort((a, b) => a.displayName.localeCompare(b.displayName)));
    } catch (e) {
      setSkillNotice(
        translateTenantAdmin(locale, "page.skillsLoadFailed", {
          error: e instanceof Error ? e.message : translateTenantAdmin(locale, "common.error"),
        }),
      );
    }
  }, [locale]);

  useEffect(() => {
    if (!authLoading && user) {
      void loadTenants();
      void loadSkills();
    }
  }, [authLoading, user, loadTenants, loadSkills]);

  function afterMutation(message: string) {
    setNotice(message);
    setPanel({ mode: "none" });
    void loadTenants();
  }

  if (authLoading || status.kind === "loading") {
    return <Centered>{t("page.loading")}</Centered>;
  }
  if (!user) return <SignInRequired />;
  if (status.kind === "forbidden") {
    return (
      <Centered>
        <div className="max-w-md text-center">
          <h1 className="mb-2 text-lg font-semibold">{t("page.adminOnly")}</h1>
          <p className="text-sm text-muted-foreground">{t("page.adminOnlyDescription")}</p>
        </div>
      </Centered>
    );
  }
  if (status.kind === "error") {
    return (
      <Centered>
        <div className="text-center">
          <p className="mb-3 text-sm text-red-600">
            {t("page.loadTenantsFailed", { error: status.message })}
          </p>
          <button className="rounded border px-3 py-1.5 text-sm" onClick={() => void loadTenants()}>
            {t("page.retry")}
          </button>
        </div>
      </Centered>
    );
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{t("page.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("page.description")}</p>
        </div>
        <button
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground"
          onClick={() => {
            setNotice(null);
            setPanel({ mode: "new" });
          }}
        >
          {t("page.newTenant")}
        </button>
      </header>

      {notice && (
        <div className="mb-4 rounded-md border bg-muted/40 px-3 py-2 text-sm" role="status">
          {notice}
        </div>
      )}
      {skillNotice && (
        <div
          className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700"
          role="status"
        >
          {skillNotice}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2">{t("page.domain")}</th>
              <th className="px-3 py-2">{t("page.documentsBucket")}</th>
              <th className="px-3 py-2">{t("page.health")}</th>
              <th className="px-3 py-2">{t("page.landingSkill")}</th>
              <th className="px-3 py-2">{t("page.enabledSkills")}</th>
              <th className="px-3 py-2">{t("page.groupTags")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {tenants.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-muted-foreground" colSpan={7}>
                  {t("page.noTenants")}
                </td>
              </tr>
            )}
            {tenants.map((tenant) => (
              <tr key={tenant.domain} className="border-t align-top">
                <td className="px-3 py-2 font-medium">
                  {tenant.domain}
                  {tenant.display_name ? (
                    <span className="block text-xs font-normal text-muted-foreground">
                      {tenant.display_name}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  {tenant.documents_bucket ? (
                    <span className="inline-flex items-center gap-1.5">
                      <ReachDot state={health[tenant.domain]} />
                      <span className="font-mono text-xs">{tenant.documents_bucket}</span>
                    </span>
                  ) : (
                    <Dim>—</Dim>
                  )}
                </td>
                <td className="px-3 py-2">
                  <HealthBadge state={health[tenant.domain]} />
                </td>
                <td className="px-3 py-2">{tenant.default_skill || <Dim>—</Dim>}</td>
                <td className="px-3 py-2">
                  {tenant.enabled_skills?.length ? tenant.enabled_skills.join(", ") : <Dim>{t("page.allSkills")}</Dim>}
                </td>
                <td className="px-3 py-2">
                  {tenant.derived_group_tags?.length ? tenant.derived_group_tags.join(", ") : <Dim>—</Dim>}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <button
                    className="rounded border px-2 py-1 text-xs"
                    onClick={() => {
                      setNotice(null);
                      setPanel({ mode: "access", tenant });
                    }}
                    title={t("page.accessTitle")}
                  >
                    {t("page.whatUsersSee")}
                  </button>
                  <button
                    className="ml-2 rounded border px-2 py-1 text-xs"
                    onClick={() => {
                      setNotice(null);
                      setPanel({ mode: "edit", tenant });
                    }}
                  >
                    {t("page.edit")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {panel.mode === "new" && (
        <TenantOnboardWizard
          availableSkills={skills}
          onCreated={() => afterMutation(t("page.onboarded"))}
          onCancel={() => setPanel({ mode: "none" })}
        />
      )}
      {panel.mode === "access" && (
        <div className="mt-4" key={`access-${panel.tenant.domain}`}>
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold">{panel.tenant.domain}</h2>
            <button className="text-xs underline" onClick={() => setPanel({ mode: "none" })}>
              {t("page.close")}
            </button>
          </div>
          <EffectiveAccessPanel domain={panel.tenant.domain} />
        </div>
      )}
      {panel.mode === "edit" && (
        <TenantEditor
          key={`edit-${panel.tenant.domain}`}
          tenant={panel.tenant}
          availableSkills={skills}
          onSaved={() => void loadTenants()}
          onDeleted={() => afterMutation(t("page.deleted", { domain: panel.tenant.domain }))}
          onCancel={() => setPanel({ mode: "none" })}
        />
      )}
    </main>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>;
}

function Dim({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}
