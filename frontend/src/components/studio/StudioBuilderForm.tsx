"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  combineInstructions,
  parseInstructions,
  type StructuredInstructions,
} from "@/components/studio/structuredInstructions";
import { A2UIConfigEditor } from "@/components/studio/A2UIConfigEditor";
import { McpBindingPicker } from "@/components/studio/McpBindingPicker";
import { DelegationEditor } from "@/components/studio/DelegationEditor";
import { AccessControlEditor } from "@/components/studio/AccessControlEditor";
import type { StudioDraft } from "@/components/studio/applyProposal";
import type { InteractionStyle, SkillVoiceConfig } from "@/types/skill";
import { DEFAULT_AVATARS } from "@/lib/defaultAvatars";
import { fetchWithAuth } from "@/lib/apiClient";
import { useI18n } from "@/contexts/I18nContext";
import {
  translateSkillStudio,
  type SkillStudioTranslationKey,
} from "@/lib/i18n/skillStudio";
import type { TranslationParams } from "@/lib/i18n";

const INTERACTION_STYLES: InteractionStyle[] = ["concise", "rigorous", "warm", "socratic"];

function useStudioT() {
  const { locale } = useI18n();
  return (key: SkillStudioTranslationKey, params?: TranslationParams) =>
    translateSkillStudio(locale, key, params);
}

export function StudioBuilderForm({
  draft,
  setDraft,
  isNew,
}: {
  draft: StudioDraft;
  setDraft: React.Dispatch<React.SetStateAction<StudioDraft>>;
  isNew: boolean;
}) {
  const t = useStudioT();
  const set = (patch: Partial<StudioDraft>) => setDraft((prev) => ({ ...prev, ...patch }));
  const setMeta = (patch: Partial<NonNullable<StudioDraft["skillMetadata"]>>) =>
    setDraft((prev) => ({ ...prev, skillMetadata: { ...prev.skillMetadata, ...patch } }));
  const setPersona = (patch: Partial<NonNullable<StudioDraft["persona"]>>) =>
    setDraft((prev) => ({ ...prev, persona: { ...prev.persona, ...patch } }));
  const setVoice = (
    patch: Partial<NonNullable<NonNullable<StudioDraft["persona"]>["voice"]>>,
  ) =>
    setDraft((prev) => ({
      ...prev,
      persona: { ...prev.persona, voice: { ...prev.persona?.voice, ...patch } },
    }));
  const setWelcome = (patch: Partial<NonNullable<StudioDraft["welcome"]>>) =>
    setDraft((prev) => ({ ...prev, welcome: { ...prev.welcome, ...patch } }));

  // Only a folder path/label is authored here. The backend resolves the bucket
  // from the viewer's tenant, preserving tenant isolation.
  const setLibrary = (
    patch: Partial<NonNullable<NonNullable<StudioDraft["welcome"]>["bucketBrowser"]>>,
  ) =>
    setDraft((prev) => {
      const next = { ...prev.welcome?.bucketBrowser, ...patch };
      const configured = Boolean(next.rootPath?.trim() || next.label?.trim());
      return {
        ...prev,
        welcome: { ...prev.welcome, bucketBrowser: configured ? next : null },
      };
    });

  const model = draft.skillMetadata?.model ?? "smart";
  const tools = draft.skillMetadata?.tools ?? [];
  const persona = draft.persona ?? {};
  const voice = persona.voice ?? {};

  return (
    <form className="space-y-6 p-4" onSubmit={(e) => e.preventDefault()}>
      <div id="studio-overview" className="scroll-mt-4 space-y-4 rounded-lg border bg-card/30 p-4">
        <div>
          <h2 className="text-sm font-semibold">{t("studio.nav.overview")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("studio.compatibilityNotice")}</p>
        </div>
        {isNew && (
          <Field label={t("builder.name")} hint={t("builder.nameHint")}>
            <input type="text" value={draft.name ?? ""} onChange={(e) => set({ name: e.target.value })}
              className="w-full rounded-md border px-3 py-2 text-sm" placeholder="my-new-skill" />
          </Field>
        )}
        <Field label={t("builder.displayName")}>
          <input type="text" value={draft.displayName ?? ""} onChange={(e) => set({ displayName: e.target.value })}
            className="w-full rounded-md border px-3 py-2 text-sm" />
        </Field>
        <Field label={t("builder.description")}>
          <input type="text" value={draft.description ?? ""} onChange={(e) => set({ description: e.target.value })}
            className="w-full rounded-md border px-3 py-2 text-sm" />
        </Field>
        <CategoryPicker value={draft.skillMetadata?.category ?? ""} onChange={(next) => setMeta({ category: next || null })} />
      </div>

      <div id="studio-prompt" className="scroll-mt-4 rounded-lg border bg-card/30 p-4">
        <h2 className="mb-3 text-sm font-semibold">{t("studio.nav.prompt")}</h2>
        <InstructionsEditor value={draft.instructions ?? ""} onChange={(v) => set({ instructions: v })} />
      </div>

      <div id="studio-model" className="scroll-mt-4 rounded-lg border bg-card/30 p-4">
        <h2 className="mb-3 text-sm font-semibold">{t("studio.nav.model")}</h2>
        <ModelTierPicker value={model} onChange={(tier) => setMeta({ model: tier })} />
      </div>

      <div id="studio-capabilities" className="scroll-mt-4 space-y-4 rounded-lg border bg-card/30 p-4">
        <h2 className="text-sm font-semibold">{t("studio.nav.capabilities")}</h2>
        <ToolsPicker selected={tools} onChange={(next) => setMeta({ tools: next })} />
        <McpBindingPicker draft={draft} setDraft={setDraft} />
        <A2UIConfigEditor draft={draft} setDraft={setDraft} />
        <DelegationEditor value={draft.skillMetadata?.delegation} currentSkillId={draft.skillId} onChange={(next) => setMeta({ delegation: next })} />
      </div>

      <div id="studio-permissions" className="scroll-mt-4 rounded-lg border bg-card/30 p-4">
        <h2 className="mb-3 text-sm font-semibold">{t("studio.nav.permissions")}</h2>
        <AccessControlEditor value={draft.accessControl} onChange={(next) => set({ accessControl: next })} />
      </div>

      <div id="studio-interaction" className="scroll-mt-4 space-y-4 rounded-lg border bg-card/30 p-4">
        <h2 className="text-sm font-semibold">{t("studio.nav.interaction")}</h2>
      <fieldset className="space-y-4 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("builder.persona")}</legend>
        <AvatarPicker value={persona.avatar ?? ""} onChange={(v) => setPersona({ avatar: v })} />
        <Field label={t("builder.interactionStyle")}>
          <select
            value={persona.interactionStyle ?? "concise"}
            onChange={(e) => setPersona({ interactionStyle: e.target.value as InteractionStyle })}
            className="w-full rounded-md border px-3 py-2 text-sm"
          >
            {INTERACTION_STYLES.map((style) => (
              <option key={style} value={style}>
                {t(`builder.interaction.${style}` as SkillStudioTranslationKey)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("builder.bio")}>
          <input
            type="text"
            value={persona.bio ?? ""}
            onChange={(e) => setPersona({ bio: e.target.value })}
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
        </Field>
        <VoicePicker voice={voice} onChange={(patch) => setVoice(patch)} />
      </fieldset>

      <Field label={t("builder.welcomeIntro")}>
        <textarea
          value={draft.welcome?.introMessage ?? ""}
          onChange={(e) => setWelcome({ introMessage: e.target.value })}
          rows={3}
          className="w-full rounded-md border px-3 py-2 text-sm"
        />
      </Field>

      <fieldset id="studio-knowledge" className="space-y-3 border-t pt-4">
        <legend className="text-sm font-medium">{t("builder.documentLibrary")}</legend>
        <p className="text-xs text-muted-foreground">{t("builder.documentLibraryDescription")}</p>
        <Field label={t("builder.folderPath")} hint={t("builder.folderPathHint")}>
          <input
            type="text"
            value={draft.welcome?.bucketBrowser?.rootPath ?? ""}
            onChange={(e) => setLibrary({ rootPath: e.target.value })}
            placeholder="documents/PPAs/longform/"
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
        </Field>
        <Field label={t("builder.libraryName")} hint={t("builder.libraryNameHint")}>
          <input
            type="text"
            value={draft.welcome?.bucketBrowser?.label ?? ""}
            onChange={(e) => setLibrary({ label: e.target.value })}
            placeholder={t("builder.libraryPlaceholder")}
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.welcome?.bucketBrowser?.defaultOpen ?? false}
            onChange={(e) => setLibrary({ defaultOpen: e.target.checked })}
          />
          {t("builder.libraryAutoOpen")}
        </label>
      </fieldset>
      </div>
      <div id="studio-advanced" className="scroll-mt-4 rounded-lg border border-dashed bg-card/20 p-4">
        <h2 className="text-sm font-semibold">{t("studio.nav.advanced")}</h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("studio.compatibilityNotice")}</p>
      </div>
    </form>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{label}</span>
      {hint && <span className="ml-2 text-xs text-muted-foreground">{hint}</span>}
      {children}
    </label>
  );
}

function CategoryPicker({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const t = useStudioT();
  const options = [
    { value: "", label: t("category.none") },
    { value: "assistant", label: t("category.assistant") },
    { value: "specialist", label: t("category.specialist") },
    { value: "tool", label: t("category.tool") },
  ];
  return (
    <Field label={t("category.label")} hint={t("category.hint")}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </Field>
  );
}

function AvatarPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const t = useStudioT();
  return (
    <div className="space-y-2">
      <div>
        <span className="text-sm font-medium">{t("avatar.label")}</span>
        <span className="ml-2 text-xs text-muted-foreground">{t("avatar.hint")}</span>
      </div>
      <div className="flex flex-wrap gap-3">
        {DEFAULT_AVATARS.map((a) => {
          const selected = value === a.src;
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => onChange(a.src)}
              title={a.label}
              aria-label={a.label}
              aria-pressed={selected}
              className={`h-16 w-16 overflow-hidden rounded-full border-2 transition ${selected ? "border-primary ring-2 ring-primary" : "border-transparent hover:border-muted-foreground/40"}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={a.src} alt={a.label} className="h-full w-full object-cover" />
            </button>
          );
        })}
      </div>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border px-3 py-2 text-sm"
        placeholder={t("avatar.placeholder")}
      />
    </div>
  );
}

interface VoiceEntry {
  name: string;
  provider: string;
  tier: string;
  gender: string;
  label: string;
}
interface VoicesResponse {
  languages: string[];
  voices: Record<string, VoiceEntry[]>;
}

const LANGUAGE_KEYS: Record<string, SkillStudioTranslationKey> = {
  es: "voice.spanish",
  en: "voice.englishUk",
  de: "voice.german",
  fr: "voice.french",
  it: "voice.italian",
  nl: "voice.dutch",
  da: "voice.danish",
};

function personaOf(voiceName?: string | null): string | null {
  if (!voiceName) return null;
  const m = voiceName.match(/-Chirp3-HD-(.+)$/);
  return m ? m[1] : null;
}

function VoicePicker({
  voice,
  onChange,
}: {
  voice: Partial<SkillVoiceConfig>;
  onChange: (patch: Partial<SkillVoiceConfig>) => void;
}) {
  const t = useStudioT();
  const [data, setData] = useState<VoicesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWithAuth("/api/proxy/api/voice/voices")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: VoicesResponse) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, []);

  const languages = data?.languages ?? [];
  const enabled = voice.enabled !== false;
  const langFromVoice = (() => {
    if (!voice.ttsVoice || !data) return null;
    return data.languages.find((l) => data.voices[l]?.some((v) => v.name === voice.ttsVoice)) ?? null;
  })();
  const selectedLang = voice.language && languages.includes(voice.language)
    ? voice.language
    : (langFromVoice ?? languages[0] ?? "");
  const langVoices = data?.voices[selectedLang] ?? [];
  const persona = personaOf(voice.ttsVoice);
  const selectedVoiceName =
    langVoices.find((v) => v.name === voice.ttsVoice)?.name ??
    langVoices.find((v) => personaOf(v.name) === persona)?.name ??
    langVoices[0]?.name ?? "";

  const applyVoice = (name: string, lang: string) => {
    const entry = data?.voices[lang]?.find((v) => v.name === name);
    onChange({ ttsVoice: name, ttsProvider: entry?.provider ?? "gcp_chirp3hd", language: lang });
  };
  const onLangChange = (lang: string) => {
    const p = personaOf(selectedVoiceName);
    const match = data?.voices[lang]?.find((v) => personaOf(v.name) === p) ?? data?.voices[lang]?.[0];
    if (match) applyVoice(match.name, lang);
    else onChange({ language: lang });
  };

  return (
    <div className="space-y-2">
      <div>
        <span className="text-sm font-medium">{t("voice.label")}</span>
        <span className="ml-2 text-xs text-muted-foreground">{t("voice.hint")}</span>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => onChange({ enabled: e.target.checked })} />
        <span>{t("voice.enable")}</span>
      </label>
      {error && <p className="text-xs text-destructive">{t("voice.loadFailed", { error })}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("voice.language")}>
          <select
            value={selectedLang}
            onChange={(e) => onLangChange(e.target.value)}
            disabled={!data || !enabled}
            className="w-full rounded-md border px-3 py-2 text-sm disabled:opacity-50"
          >
            {languages.map((l) => (
              <option key={l} value={l}>{LANGUAGE_KEYS[l] ? t(LANGUAGE_KEYS[l]) : l}</option>
            ))}
          </select>
        </Field>
        <Field label={t("voice.label")}>
          <select
            value={selectedVoiceName}
            onChange={(e) => applyVoice(e.target.value, selectedLang)}
            disabled={!data || !enabled}
            className="w-full rounded-md border px-3 py-2 text-sm disabled:opacity-50"
          >
            {langVoices.map((v) => <option key={v.name} value={v.name}>{v.label}</option>)}
          </select>
        </Field>
      </div>
    </div>
  );
}

const INSTRUCTION_FIELD_KEYS: {
  key: Exclude<keyof StructuredInstructions, "additional">;
  label: SkillStudioTranslationKey;
  hint: SkillStudioTranslationKey;
  placeholder: SkillStudioTranslationKey;
  rows: number;
}[] = [
  { key: "goal", label: "instructions.goal", hint: "instructions.goalHint", placeholder: "instructions.goalPlaceholder", rows: 2 },
  { key: "guidelines", label: "instructions.guidelines", hint: "instructions.guidelinesHint", placeholder: "instructions.guidelinesPlaceholder", rows: 4 },
  { key: "constraints", label: "instructions.constraints", hint: "instructions.constraintsHint", placeholder: "instructions.constraintsPlaceholder", rows: 3 },
  { key: "outputFormat", label: "instructions.outputFormat", hint: "instructions.outputFormatHint", placeholder: "instructions.outputFormatPlaceholder", rows: 2 },
];

function InstructionsEditor({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const t = useStudioT();
  const [fields, setFields] = useState<StructuredInstructions>(() => parseInstructions(value));
  const lastCombined = useRef(value);

  useEffect(() => {
    if (value !== lastCombined.current) {
      setFields(parseInstructions(value));
      lastCombined.current = value;
    }
  }, [value]);

  const update = (patch: Partial<StructuredInstructions>) => {
    const next = { ...fields, ...patch };
    setFields(next);
    const combined = combineInstructions(next);
    lastCombined.current = combined;
    onChange(combined);
  };

  return (
    <fieldset className="space-y-4 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">{t("instructions.title")}</legend>
      <p className="text-xs text-muted-foreground">{t("instructions.description")}</p>
      {INSTRUCTION_FIELD_KEYS.map((f) => (
        <Field key={f.key} label={t(f.label)} hint={t(f.hint)}>
          <textarea
            value={fields[f.key]}
            onChange={(e) => update({ [f.key]: e.target.value } as Partial<StructuredInstructions>)}
            rows={f.rows}
            className="w-full rounded-md border px-3 py-2 text-sm"
            placeholder={t(f.placeholder)}
          />
        </Field>
      ))}
      {fields.additional.trim() !== "" && (
        <Field label={t("instructions.additional")} hint={t("instructions.additionalHint")}>
          <textarea
            value={fields.additional}
            onChange={(e) => update({ additional: e.target.value })}
            rows={4}
            className="w-full rounded-md border px-3 py-2 font-mono text-sm"
          />
        </Field>
      )}
    </fieldset>
  );
}

interface ModelInfo { id: string; description?: string; provider?: string; tier?: string; }
interface ModelsApiResponse { models: ModelInfo[]; tier_defaults: Record<string, string>; }
type TierOption = { tier: string; model: string; desc: string };
const TIER_ORDER = ["smart", "pro", "lite"];
const FALLBACK_TIERS: TierOption[] = [
  { tier: "smart", model: "claude-opus-4-8", desc: "" },
  { tier: "pro", model: "gemini-2.5-pro", desc: "" },
  { tier: "lite", model: "gemini-flash-lite", desc: "" },
];
const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic — Claude",
  openai: "OpenAI — GPT",
  google: "Google — Gemini",
};
const PROVIDER_ORDER = ["anthropic", "openai", "google"];

function ModelTierPicker({ value, onChange }: { value: string; onChange: (tier: string) => void }) {
  const t = useStudioT();
  const [tiers, setTiers] = useState<TierOption[] | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchWithAuth("/api/proxy/api/models")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: ModelsApiResponse) => {
        if (cancelled) return;
        const byId = new Map(data.models.map((m) => [m.id, m.description ?? m.id]));
        const list = Object.entries(data.tier_defaults ?? {}).map(([tier, id]) => ({ tier, model: id, desc: byId.get(id) ?? id }));
        list.sort((a, b) => TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier));
        setTiers(list.length > 0 ? list : FALLBACK_TIERS);
        setModels(data.models ?? []);
      })
      .catch(() => { if (!cancelled) setTiers(FALLBACK_TIERS); });
    return () => { cancelled = true; };
  }, []);

  const tierList = tiers ?? FALLBACK_TIERS;
  const byProvider: Record<string, ModelInfo[]> = {};
  for (const m of models) {
    const p = m.provider ?? "other";
    (byProvider[p] ??= []).push(m);
  }
  const known = tierList.some((x) => x.tier === value) || models.some((m) => m.id === value);
  const currentTier = tierList.find((x) => x.tier === value);
  const tierLabel = (tier: string) => {
    if (tier === "smart") return t("model.smart");
    if (tier === "pro") return t("model.pro");
    if (tier === "lite") return t("model.lite");
    return tier;
  };
  const tierBlurb = (tier: string, fallback: string) => {
    if (tier === "smart") return t("model.smartBlurb");
    if (tier === "pro") return t("model.proBlurb");
    if (tier === "lite") return t("model.liteBlurb");
    return fallback;
  };

  return (
    <Field label={t("model.label")} hint={t("model.hint")}>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
        <optgroup label={t("model.tiers")}>
          {tierList.map((tier) => <option key={tier.tier} value={tier.tier}>{tierLabel(tier.tier)} · {tier.model}</option>)}
        </optgroup>
        {PROVIDER_ORDER.filter((p) => byProvider[p]?.length).map((p) => (
          <optgroup key={p} label={PROVIDER_LABELS[p] ?? p}>
            {byProvider[p].map((m) => <option key={m.id} value={m.id}>{m.id}{m.description ? ` — ${m.description}` : ""}</option>)}
          </optgroup>
        ))}
        {!known && value ? <option value={value}>{value}</option> : null}
      </select>
      <span className="mt-1 block text-xs text-muted-foreground">
        {currentTier ? tierBlurb(currentTier.tier, currentTier.desc) : t("model.pinned")}
      </span>
    </Field>
  );
}

interface ToolInfo { name: string; label: string; description: string; category: string; }

function ToolsPicker({ selected, onChange }: { selected: string[]; onChange: (next: string[]) => void }) {
  const t = useStudioT();
  const [catalog, setCatalog] = useState<ToolInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWithAuth("/api/proxy/api/tools")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: { tools: ToolInfo[] }) => { if (!cancelled) setCatalog(data.tools ?? []); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, []);

  const toggle = (name: string, on: boolean) => onChange(
    on ? [...selected.filter((x) => x !== name), name] : selected.filter((x) => x !== name),
  );
  const groups: { category: string; tools: ToolInfo[] }[] = [];
  for (const tool of catalog ?? []) {
    let group = groups.find((x) => x.category === tool.category);
    if (!group) { group = { category: tool.category, tools: [] }; groups.push(group); }
    group.tools.push(tool);
  }
  const catalogNames = new Set((catalog ?? []).map((x) => x.name));
  const extras = selected.filter((name) => !catalogNames.has(name));

  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">{t("tools.title")}</legend>
      <p className="text-xs text-muted-foreground">{t("tools.description")}</p>
      {catalog === null && !error && <p className="text-xs text-muted-foreground">{t("tools.loading")}</p>}
      {error && <p className="text-xs text-destructive">{t("tools.loadFailed", { error })}</p>}
      {groups.map((group) => (
        <div key={group.category} className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.category}</p>
          {group.tools.map((tool) => (
            <label key={tool.name} className="flex items-start gap-2">
              <input type="checkbox" checked={selected.includes(tool.name)} onChange={(e) => toggle(tool.name, e.target.checked)} className="mt-1" />
              <span>
                <span className="text-sm font-medium">{tool.label}</span>
                <span className="block text-xs text-muted-foreground">{tool.description}</span>
              </span>
            </label>
          ))}
        </div>
      ))}
      {extras.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("tools.advanced")}</p>
          {extras.map((name) => (
            <label key={name} className="flex items-start gap-2">
              <input type="checkbox" checked onChange={() => toggle(name, false)} className="mt-1" />
              <span className="font-mono text-sm">{name}</span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}

