// TenantEditor — edit an existing tenant config and validate it in place.
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

interface Draft {
  display_name: string;
  documents_bucket: string;
  default_skill: string;
  enabled_skills: string[];
  derived_group_tags: string;
}

function toDraft(c: ClientConfig): Draft {
  return {
    display_name: c.display_name ?? "",
    documents_bucket: c.documents_bucket ?? "",
    default_skill: c.default_skill ?? "",
    enabled_skills: c.enabled_skills ?? [],
    derived_group_tags: (c.derived_group_tags ?? []).join(", "),
  };
}

export function TenantEditor({
  tenant,
  availableSkills,
  onSaved,
  onCancel,
  onDeleted,
}: {
  tenant: ClientConfig;
  availableSkills: SkillOption[];
  onSaved: () => void;
  onCancel: () => void;
  onDeleted: () => void;
}) {
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translateTenantAdmin>[1],
    params: Record<string, string | number> = {},
  ) => translateTenantAdmin(locale, key, params);
  const [draft, setDraft] = useState<Draft>(() => toDraft(tenant));
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [badRefs, setBadRefs] = useState<string[]>([]);
  const [validation, setValidation] = useState<TenantValidation | null>(null);

  async function save() {
    setSaving(true);
    setNotice(null);
    setBadRefs([]);
    try {
      const body = {
        display_name: draft.display_name.trim(),
        documents_bucket: draft.documents_bucket.trim() || null,
        default_skill: draft.default_skill.trim() || null,
        enabled_skills: draft.enabled_skills.length ? draft.enabled_skills : null,
        derived_group_tags: csvToList(draft.derived_group_tags),
      };
      const r = await fetchWithAuth(
        `/api/proxy/api/admin/clients/${encodeURIComponent(tenant.domain)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (r.status === 403) {
        setNotice(t("editor.forbiddenSave"));
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
        setNotice(t("editor.saveFailedHttp", { status: r.status }));
        return;
      }
      onSaved();
      await validate();
      setNotice(t("editor.saved"));
    } catch (e) {
      setNotice(t("editor.saveFailed", { error: e instanceof Error ? e.message : t("common.error") }));
    } finally {
      setSaving(false);
    }
  }

  async function validate() {
    setValidating(true);
    setNotice(null);
    setValidation(null);
    try {
      const r = await fetchWithAuth(
        `/api/proxy/api/admin/tenants/${encodeURIComponent(tenant.domain)}/validate`,
      );
      if (r.status === 403) {
        setNotice(t("editor.forbiddenValidate"));
        return;
      }
      if (r.status === 404) {
        setNotice(t("editor.saveFirst"));
        return;
      }
      if (!r.ok) {
        setNotice(t("editor.validationFailedHttp", { status: r.status }));
        return;
      }
      setValidation((await r.json()) as TenantValidation);
    } catch (e) {
      setNotice(
        t("editor.validationFailed", { error: e instanceof Error ? e.message : t("common.error") }),
      );
    } finally {
      setValidating(false);
    }
  }

  async function remove() {
    if (!window.confirm(t("editor.deleteConfirm", { domain: tenant.domain }))) return;
    setNotice(null);
    try {
      const r = await fetchWithAuth(
        `/api/proxy/api/admin/clients/${encodeURIComponent(tenant.domain)}`,
        { method: "DELETE" },
      );
      if (!r.ok && r.status !== 404) {
        setNotice(t("editor.deleteFailedHttp", { status: r.status }));
        return;
      }
      onDeleted();
    } catch (e) {
      setNotice(t("editor.deleteFailed", { error: e instanceof Error ? e.message : t("common.error") }));
    }
  }

  return (
    <section className="mt-6 rounded-lg border p-4">
      <h2 className="mb-3 text-base font-semibold">{t("editor.title", { domain: tenant.domain })}</h2>

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
            {draft.default_skill &&
              !availableSkills.some((s) => s.slug === draft.default_skill) && (
                <option value={draft.default_skill}>
                  {t("editor.notInCatalog", { slug: draft.default_skill })}
                </option>
              )}
          </select>
        </Field>
        <Field label={t("common.documentsBucket")} hint={t("editor.bucketHint")}>
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
          <Field label={t("common.enabledSkills")} hint={t("editor.enabledHint")}>
            <SkillMultiSelect
              options={availableSkills}
              selected={draft.enabled_skills}
              onChange={(next) => setDraft({ ...draft, enabled_skills: next })}
            />
          </Field>
        </div>
      </div>

      {validation && (
        <div className="mt-4">
          <ValidationVerdicts validation={validation} />
        </div>
      )}

      <div className="mt-4 flex items-center gap-2">
        <button
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-60"
          onClick={() => void save()}
          disabled={saving}
        >
          {saving ? t("editor.saving") : t("editor.save")}
        </button>
        <button
          className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-60"
          onClick={() => void validate()}
          disabled={validating}
        >
          {validating ? t("editor.validating") : t("editor.validate")}
        </button>
        <button className="rounded-md border px-3 py-1.5 text-sm" onClick={onCancel}>
          {t("common.cancel")}
        </button>
        <button
          className="ml-auto rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-600"
          onClick={() => void remove()}
        >
          {t("editor.delete")}
        </button>
      </div>
    </section>
  );
}
