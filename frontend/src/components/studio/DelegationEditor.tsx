// SKILL-DELEGATION M4 — Skill Studio delegation editor.

"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";
import type { DelegateEntry, DelegationConfig } from "@/types/skill";

const entryId = (e: DelegateEntry): string => (typeof e === "string" ? e : (e?.skill ?? ""));

interface SkillOption {
  id: string;
  label: string;
}

interface DelegationEditorProps {
  value?: DelegationConfig;
  currentSkillId?: string;
  onChange: (next: DelegationConfig) => void;
}

const DEFAULT: DelegationConfig = { enabled: false, mode: "auto", allow: [], maxDepth: 1 };

export function DelegationEditor({ value, currentSkillId, onChange }: DelegationEditorProps) {
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translateSkillStudio>[1],
    params: Record<string, string | number> = {},
  ) => translateSkillStudio(locale, key, params);
  const cfg: DelegationConfig = { ...DEFAULT, ...value };
  const [skills, setSkills] = useState<SkillOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchWithAuth("/api/proxy/api/skills");
        const data: unknown = await res.json();
        const list: SkillOption[] = (Array.isArray(data) ? data : [])
          .map((s) => {
            const r = s as { skillId?: string; id?: string; displayName?: string; name?: string };
            const id = r.skillId ?? r.id ?? "";
            return { id, label: r.displayName || r.name || id };
          })
          .filter((s) => s.id && s.id !== currentSkillId);
        if (!cancelled) setSkills(list);
      } catch {
        if (!cancelled) setSkills([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentSkillId]);

  const allowEntries: DelegateEntry[] = Array.isArray(cfg.allow) ? cfg.allow : [];
  const allowIds = allowEntries.map(entryId).filter(Boolean);

  const update = (patch: Partial<DelegationConfig>) => onChange({ ...cfg, ...patch });
  const toggleAllow = (id: string) =>
    update({
      allow: allowIds.includes(id)
        ? allowEntries.filter((e) => entryId(e) !== id)
        : [...allowEntries, id],
    });

  const known = new Set(skills.map((s) => s.id));
  const orphanAllowed = allowIds.filter((id) => !known.has(id));

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t("delegation.title")}</h3>
          <p className="text-xs text-muted-foreground">{t("delegation.description")}</p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={cfg.enabled}
            onChange={(e) => update({ enabled: e.target.checked })}
            aria-label={t("delegation.enableAria")}
          />
          {t("delegation.enabled")}
        </label>
      </div>

      {cfg.enabled && (
        <div className="flex flex-col gap-3 rounded-md border border-border p-3">
          <fieldset className="flex flex-col gap-1">
            <legend className="mb-1 text-xs font-medium text-muted-foreground">{t("delegation.when")}</legend>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="radio"
                name="delegation-mode"
                checked={cfg.mode === "auto"}
                onChange={() => update({ mode: "auto" })}
              />
              <span>
                <span className="font-medium">{t("delegation.auto")}</span> — {t("delegation.autoDescription")}
              </span>
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="radio"
                name="delegation-mode"
                checked={cfg.mode === "suggest"}
                onChange={() => update({ mode: "suggest" })}
              />
              <span>
                <span className="font-medium">{t("delegation.suggest")}</span> — {t("delegation.suggestDescription")}
              </span>
            </label>
          </fieldset>

          <div className="flex flex-col gap-1">
            <div className="text-xs font-medium text-muted-foreground">
              {t("delegation.canHandOff", { count: allowIds.length > 0 ? `(${allowIds.length})` : "" })}
            </div>
            {loading ? (
              <p className="text-xs text-muted-foreground/70">{t("delegation.loading")}</p>
            ) : skills.length === 0 && orphanAllowed.length === 0 ? (
              <p className="text-xs text-muted-foreground/70">{t("delegation.none")}</p>
            ) : (
              <ul className="flex max-h-56 flex-col gap-0.5 overflow-auto rounded border border-border p-1.5">
                {skills.map((s) => (
                  <li key={s.id}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-muted/40">
                      <input
                        type="checkbox"
                        checked={allowIds.includes(s.id)}
                        onChange={() => toggleAllow(s.id)}
                      />
                      <span className="truncate">{s.label}</span>
                    </label>
                  </li>
                ))}
                {orphanAllowed.map((id) => (
                  <li key={id}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs text-muted-foreground/70 hover:bg-muted/40">
                      <input type="checkbox" checked onChange={() => toggleAllow(id)} />
                      <span className="truncate font-mono">{id}</span>
                      <span className="text-[10px]">{t("delegation.noAccess")}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[10px] text-muted-foreground/60">{t("delegation.ceiling")}</p>
          </div>
        </div>
      )}
    </section>
  );
}
