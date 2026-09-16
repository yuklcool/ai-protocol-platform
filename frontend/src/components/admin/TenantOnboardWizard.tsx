// TenantOnboardWizard — atomic tenant onboarding via POST /api/admin/tenants.
"use client";

import { useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { translateTenantAdmin } from "@/lib/i18n/tenantAdmin";
import {
  BadRefNotice,
  ClientConfig,
  csvToList,
  detailMessage,
  Field,
  parseUnknownSkillRefs,
  SkillMultiSelect,
  SkillOption,
  TenantValidation,
  ValidationVerdicts,
} from "./tenantAdmin";

interface OnboardResponse {
  domain: string;
  config: ClientConfig;
  validation: TenantValidation;
}

interface Draft {
  domain: string;
  display_name: string;
  documents_bucket: string;
  default_skill: string;
  enabled_skills: string[];
  derived_group_tags: string;
}

const EMPTY: Draft = {
  domain: "",
  display_name: "",
  documents_bucket: "",
  default_skill: "",
  enabled_skills: [],
  derived_group_tags: "",
};

export function TenantOnboardWizard({
  availableSkills,
  onCreated,
  onCancel,
}: {
  availableSkills: SkillOption[];
  onCreated: () => void;
  onCancel: () => void;
}) {
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translateTenantAdmin>[1],
    params: Record<string, string | number> = {},
  ) => translateTenantAdmin(locale, key, params);
  const [draft, setDraft] = useState<Draft>({ ...EMPTY });
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [badRefs, setBadRefs] = useState<string[]>([]);
  const [result, setResult] = useState<OnboardResponse | null>(null);

  async function submit() {
    const domain = draft.domain.trim().toLowerCase();
    setNotice(null);
    setBadRefs([]);
    if (!domain || !domain.includes(".")) {
      setNotice(t("onboard.invalidDomain"));
      return;
    }
    setSubmitting(true);
    try {
      const body = {
        domain,
        display_name: draft.display_name.trim(),
        documents_bucket: draft.documents_bucket.trim() || null,
        default_skill: draft.default_skill.trim() || null,
        enabled_skills: draft.enabled_skills.length ? draft.enabled_skills : null,
        derived_group_tags: csvToList(draft.derived_group_tags),
      };
      const r = await fetchWithAuth("/api/proxy/api/admin/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.status === 403) {
        setNotice(t("onboard.forbidden"));
        return;
      }
      if (r.status === 409) {
        setNotice(t("onboard.exists", { domain }));
        return;
      }
      if (r.status === 422) {
        const data = await r.json().catch(() => ({}));
        const refs = parseUnknownSkillRefs(data?.detail);
        setBadRefs(refs);
        setNotice(refs.length ? null : detailMessage(data?.detail, t("common.validationFailed")));
        return;
      }
      if (!r.ok) {
        setNotice(t("onboard.failedHttp", { status: r.status }));
        return;
      }
      setResult((await r.json()) as OnboardResponse);
    } catch (e) {
      setNotice(t("onboard.failed", { error: e instanceof Error ? e.message : t("common.error") }));
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <section className="mt-6 rounded-lg border p-4">
        <h2 className="mb-3 text-base font-semibold">
          {t("onboard.successTitle", { domain: result.domain })}
        </h2>
        <ValidationVerdicts validation={result.validation} />
        <div className="mt-4 flex gap-2">
          <button
            className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground"
            onClick={onCreated}
          >
            {t("onboard.done")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-lg border p-4">
      <h2 className="mb-1 text-base font-semibold">{t("onboard.title")}</h2>
      <p className="mb-3 text-sm text-muted-foreground">{t("onboard.description")}</p>

      {notice && (
        <div className="mb-3 rounded-md border bg-muted/40 px-3 py-2 text-sm" role="status">
          {notice}
        </div>
      )}
      {badRefs.length > 0 && (
        <div className="mb-3">
          <BadRefNotice refs={badRefs} />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("onboard.emailDomain")} hint={t("onboard.emailDomainHint")}>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={draft.domain}
            onChange={(e) => setDraft({ ...draft, domain: e.target.value })}
            placeholder="acme-corp.com"
          />
        </Field>
        <Field label={t("common.displayName")}>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={draft.display_name}
            onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
          />
        </Field>
        <Field label={t("common.landingSkill")} hint={t("common.landingSkillHint")}>
          <select
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={draft.default_skill}
            onChange={(e) => setDraft({ ...draft, default_skill: e.target.value })}
          >
            <option value="">{t("common.marketplaceDefault")}</option>
            {availableSkills.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.displayName} ({s.slug})
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("common.documentsBucket")} hint={t("onboard.bucketHint")}>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={draft.documents_bucket}
            onChange={(e) => setDraft({ ...draft, documents_bucket: e.target.value })}
          />
        </Field>
        <Field label={t("common.derivedTags")} hint={t("common.derivedTagsHint")}>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={draft.derived_group_tags}
            onChange={(e) => setDraft({ ...draft, derived_group_tags: e.target.value })}
            placeholder="ACME"
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label={t("common.enabledSkills")} hint={t("onboard.enabledHint")}>
            <SkillMultiSelect
              options={availableSkills}
              selected={draft.enabled_skills}
              onChange={(next) => setDraft({ ...draft, enabled_skills: next })}
            />
          </Field>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <button
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-60"
          onClick={() => void submit()}
          disabled={submitting}
        >
          {submitting ? t("onboard.submitting") : t("onboard.submit")}
        </button>
        <button className="rounded-md border px-3 py-1.5 text-sm" onClick={onCancel}>
          {t("common.cancel")}
        </button>
      </div>
    </section>
  );
}
