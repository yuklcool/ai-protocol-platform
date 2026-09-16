// Skill access-control editor for Skill Studio.

"use client";

import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";

type Access = {
  type?: string;
  domain?: string | null;
  emails?: string[] | null;
  tags?: string[] | null;
};

const csv = (a?: string[] | null): string => (a ?? []).join(", ");
const toList = (s: string): string[] | null => {
  const x = s
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  return x.length ? x : null;
};

export function AccessControlEditor({
  value,
  onChange,
}: {
  value?: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateSkillStudio>[1]) => translateSkillStudio(locale, key);
  const types = [
    { v: "private", label: t("access.private") },
    { v: "public", label: t("access.public") },
    { v: "tagged", label: t("access.tagged") },
    { v: "domain", label: t("access.domain") },
    { v: "specific", label: t("access.specific") },
  ];
  const v = (value ?? { type: "private" }) as Access;
  const type = v.type ?? "private";

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="mb-1 block text-sm font-medium">{t("access.title")}</span>
        <select
          className="w-full rounded-md border px-3 py-2 text-sm"
          value={type}
          onChange={(e) => {
            const nextType = e.target.value;
            if (nextType === "public" && type !== "public") {
              const ok = window.confirm(t("access.publicConfirm"));
              if (!ok) return;
            }
            onChange({ ...v, type: nextType });
          }}
        >
          {types.map((entry) => (
            <option key={entry.v} value={entry.v}>
              {entry.label}
            </option>
          ))}
        </select>
      </label>

      {type === "tagged" && (
        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">{t("access.groupTags")}</span>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={csv(v.tags)}
            placeholder="ONE, aitana-admin"
            onChange={(e) => onChange({ ...v, tags: toList(e.target.value) })}
          />
        </label>
      )}

      {type === "domain" && (
        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">{t("access.emailDomain")}</span>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={v.domain ?? ""}
            placeholder="acmeenergy.com"
            onChange={(e) => onChange({ ...v, domain: e.target.value || null })}
          />
        </label>
      )}

      {type === "specific" && (
        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">{t("access.allowedEmails")}</span>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={csv(v.emails)}
            placeholder="alice@example.com, bob@example.com"
            onChange={(e) => onChange({ ...v, emails: toList(e.target.value) })}
          />
        </label>
      )}
    </div>
  );
}
