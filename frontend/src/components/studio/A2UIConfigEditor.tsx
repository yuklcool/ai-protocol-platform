"use client";

import type { Dispatch, SetStateAction } from "react";
import type { StudioDraft } from "./applyProposal";
import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio, type SkillStudioTranslationKey } from "@/lib/i18n/skillStudio";

const SURFACES = ["chat", "workspace", "sidebar", "modal"] as const;

export function A2UIConfigEditor({ draft, setDraft }: {
  draft: StudioDraft;
  setDraft: Dispatch<SetStateAction<StudioDraft>>;
}) {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey) => translateSkillStudio(locale, key);
  const config = draft.skillMetadata?.toolConfigs?.a2ui ?? {};
  const enabled = config.enabled !== false;
  const surface = typeof config.default_surface === "string" ? config.default_surface : "";
  const persistent = surface !== "" && surface !== "chat";
  const update = (patch: Record<string, unknown>) => setDraft((previous) => {
    const metadata = previous.skillMetadata;
    const toolConfigs = metadata?.toolConfigs;
    const a2ui = { ...toolConfigs?.a2ui, ...patch };
    // A legacy disabled config may contain patch + chat. Re-enabling it must
    // obey the same persistent-surface invariant as the backend validator.
    if (a2ui.enabled !== false && (!a2ui.default_surface || a2ui.default_surface === "chat")) {
      a2ui.default_update_mode = "replace";
    }
    return { ...previous, skillMetadata: { ...metadata, toolConfigs: { ...toolConfigs, a2ui } } };
  });

  return (
    <fieldset className="space-y-4 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">{t("a2ui.title")}</legend>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => update({ enabled: e.target.checked })} />
        {t("a2ui.enabled")}
      </label>
      <fieldset disabled={!enabled} className="space-y-3 disabled:opacity-50">
        <label className="block space-y-1 text-sm">
          <span>{t("a2ui.surface")}</span>
          <select className="w-full rounded-md border px-3 py-2" value={surface}
            onChange={(e) => update({ default_surface: e.target.value || null })}>
            <option value="">{t("a2ui.inline")}</option>
            {SURFACES.map((id) => <option key={id} value={id}>{t(`a2ui.${id}`)}</option>)}
            {surface && !SURFACES.some((id) => id === surface) && <option value={surface}>{surface}</option>}
          </select>
        </label>
        <label className="block space-y-1 text-sm">
          <span>{t("a2ui.mode")}</span>
          <select className="w-full rounded-md border px-3 py-2" value={String(config.default_update_mode ?? "replace")}
            onChange={(e) => update({ default_update_mode: e.target.value })}>
            <option value="replace">{t("a2ui.replace")}</option>
            <option value="patch" disabled={!persistent}>{t("a2ui.patch")}</option>
          </select>
        </label>
        <p className="text-xs text-muted-foreground">{t("a2ui.hint")}</p>
        {([ ["allow_surface_context_writes", "a2ui.writes"], ["allow_action_triggered_runs", "a2ui.runs"] ] as const).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={config[key] === true} onChange={(e) => update({ [key]: e.target.checked })} />
            {t(label)}
          </label>
        ))}
        <p className="text-xs text-muted-foreground">{t("a2ui.grants")}</p>
      </fieldset>
    </fieldset>
  );
}
