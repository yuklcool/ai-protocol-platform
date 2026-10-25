"use client";

import Link from "next/link";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";
import { AccessControlEditor } from "./AccessControlEditor";
import type { SkillFile, StudioDraft } from "./draft";

export function StudioBuilderForm({ draft, setDraft, isNew }: {
  draft: StudioDraft;
  setDraft: Dispatch<SetStateAction<StudioDraft>>;
  isNew: boolean;
}) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateSkillStudio>[1]) => translateSkillStudio(locale, key);
  const set = (patch: Partial<StudioDraft>) => setDraft((previous) => ({ ...previous, ...patch }));
  const control = "glass-control min-h-11 w-full px-3 py-2 text-sm";
  return (
    <form className="space-y-6" onSubmit={(event) => event.preventDefault()}>
      <p className="text-xs leading-5 text-muted-foreground">
        <span>{t("studio.capabilityNotice")} <Link href="/agent" className="inline-flex min-h-11 items-center text-primary underline underline-offset-4">{t("studio.rootSettings")}</Link></span>
      </p>
      <section className="glass-panel space-y-4 p-5">
        {isNew && <Field label={t("builder.name")}><input value={draft.name} onChange={(event) => set({ name: event.target.value })} className={control} placeholder="my-skill" /></Field>}
        <Field label={t("builder.displayName")}><input value={draft.displayName} onChange={(event) => set({ displayName: event.target.value })} className={control} /></Field>
        <Field label={t("builder.description")}><input value={draft.description} onChange={(event) => set({ description: event.target.value })} className={control} /></Field>
        <Field label={t("builder.instructions")}><textarea value={draft.instructions} onChange={(event) => set({ instructions: event.target.value })} rows={14} className={`${control} font-mono`} /></Field>
      </section>
      <details className="glass-panel">
        <summary className="min-h-11 cursor-pointer px-4 py-3 text-sm font-medium">{t("builder.files")}</summary>
        <div className="space-y-4 border-t p-4">
        <p className="mt-2 text-xs text-muted-foreground">{t("builder.filesHint")}</p>
        <FilesEditor label={t("builder.references")} files={draft.references} onChange={(references) => set({ references })} />
        <FilesEditor label={t("builder.assets")} files={draft.assets} onChange={(assets) => set({ assets })} />
        </div>
      </details>
      <section className="glass-panel space-y-4 p-5">
        <AccessControlEditor value={draft.accessControl} onChange={(accessControl) => set({ accessControl })} />
      </section>
    </form>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block space-y-1.5"><span className="text-sm font-medium">{label}</span>{children}</label>;
}

function FilesEditor({ label, files, onChange }: { label: string; files: SkillFile[]; onChange: (files: SkillFile[]) => void }) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateSkillStudio>[1]) => translateSkillStudio(locale, key);
  const update = (index: number, patch: Partial<SkillFile>) => onChange(files.map((file, position) => position === index ? { ...file, ...patch } : file));
  return (
    <fieldset className="mt-4 space-y-3">
      <legend className="text-sm font-medium">{label}</legend>
      {files.map((file, index) => (
        <div key={index} className="surface-sunken space-y-2 p-3">
          <Field label={`${label} · ${t("builder.filename")}`}><input value={file.name} onChange={(event) => update(index, { name: event.target.value })} className="glass-control min-h-11 w-full px-3 py-2 text-sm" /></Field>
          <Field label={t("builder.fileContent")}><textarea value={file.content} onChange={(event) => update(index, { content: event.target.value })} rows={5} className="glass-control min-h-11 w-full px-3 py-2 font-mono text-sm" /></Field>
          <button type="button" onClick={() => onChange(files.filter((_, position) => position !== index))} className="button-danger min-h-11 px-3 py-2 text-xs">{t("builder.removeFile")}</button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...files, { name: "", content: "" }])} className="button-secondary min-h-11 px-3 py-2 text-xs">{t("builder.addFile")}</button>
    </fieldset>
  );
}
