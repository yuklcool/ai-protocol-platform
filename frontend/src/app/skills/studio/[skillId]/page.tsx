// Skill Studio — authoring page orchestration.
//
// The builder controls live in StudioBuilderForm so the large form can evolve
// independently from load/save/fork and AG-UI orchestration. `skillId` is either
// `new` or an existing skill id. Nothing persists until Save.

"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { StudioBuilderForm } from "@/components/studio/StudioBuilderForm";
import { SkillStudioShell } from "@/components/studio/SkillStudioShell";
import { buildSaveBody, emptyDraft, skillToDraft, type StudioDraft } from "@/components/studio/draft";
import type { Skill } from "@/types/skill";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";

const STUDIO_ENABLED = process.env.NEXT_PUBLIC_ENABLE_SKILL_STUDIO === "true";

/** Sentinel owner uid for platform-owned (read-only) skills. Runtime identifier,
 * not display branding. Mirrors backend skills/platform.py PLATFORM_OWNER_UID. */
const PLATFORM_OWNER_UID = "aitana-platform";

type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "ok"; message: string }
  | { status: "error"; message: string };

export default function StudioPage({
  params,
}: {
  params: Promise<{ skillId: string }>;
}) {
  const { skillId } = use(params);
  const { locale } = useI18n();

  if (!STUDIO_ENABLED) {
    return (
      <main className="page-container flex min-h-screen items-center justify-center p-8">
        <p className="notice notice--info">
          {translateSkillStudio(locale, "studio.disabled")}
        </p>
      </main>
    );
  }

  return <StudioGate skillId={skillId} />;
}

function StudioGate({ skillId }: { skillId: string }) {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  if (loading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {translateSkillStudio(locale, "studio.loading")}
      </div>
    );
  }
  if (!user) return <SignInRequired />;
  return <StudioInner skillId={skillId} />;
}

function StudioInner({ skillId }: { skillId: string }) {
  const { locale } = useI18n();
  const isNew = skillId === "new";
  const router = useRouter();
  const [draft, setDraft] = useState<StudioDraft>(() => emptyDraft());
  const [loadingSkill, setLoadingSkill] = useState(!isNew);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  const [pristine, setPristine] = useState<string>(() => JSON.stringify(emptyDraft()));
  const [forking, setForking] = useState(false);

  const t = useCallback(
    (key: Parameters<typeof translateSkillStudio>[1], params?: Parameters<typeof translateSkillStudio>[2]) =>
      translateSkillStudio(locale, key, params),
    [locale],
  );

  useEffect(() => {
    if (isNew) return;
    let cancelled = false;
    setLoadingSkill(true);
    fetchWithAuth(`/api/proxy/api/skills/${skillId}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as Skill;
        if (cancelled) return;
        const loaded = skillToDraft(data);
        setDraft(loaded);
        setPristine(JSON.stringify(loaded));
        setLoadingSkill(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoadingSkill(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isNew, skillId]);

  const handleSave = useCallback(async () => {
    setSaveState({ status: "saving" });
    try {
      const body = buildSaveBody(draft, isNew);
      const path = isNew ? "/api/proxy/api/skills" : `/api/proxy/api/skills/${skillId}`;
      const res = await fetchWithAuth(path, {
        method: isNew ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await safeErrorDetail(res);
        setSaveState({
          status: "error",
          message: t("studio.saveFailed", {
            status: res.status,
            detail: detail ? `: ${detail}` : "",
          }),
        });
        return;
      }
      const saved = (await res.json()) as Skill;
      const savedDraft = skillToDraft(saved);
      setDraft(savedDraft);
      setPristine(JSON.stringify(savedDraft));
      setSaveState({ status: "ok", message: t("studio.saved") });
    } catch (err) {
      setSaveState({
        status: "error",
        message: err instanceof Error && err.message === "invalidSkillFiles"
          ? t("builder.invalidFiles")
          : err instanceof Error ? err.message : String(err),
      });
    }
  }, [draft, isNew, skillId, t]);

  const isDirty = useMemo(() => JSON.stringify(draft) !== pristine, [draft, pristine]);

  const handleCancel = useCallback(() => {
    if (isDirty && !window.confirm(t("studio.discardConfirm"))) return;
    router.back();
  }, [isDirty, router, t]);

  const isPlatformOwned = !isNew && draft.ownerId === PLATFORM_OWNER_UID;

  const handleFork = useCallback(async () => {
    setForking(true);
    try {
      const res = await fetchWithAuth(`/api/proxy/api/skills/${skillId}/fork`, { method: "POST" });
      if (!res.ok) {
        const detail = await safeErrorDetail(res);
        setSaveState({
          status: "error",
          message: t("studio.forkFailed", {
            status: res.status,
            detail: detail ? `: ${detail}` : "",
          }),
        });
        return;
      }
      const forked = (await res.json()) as Skill;
      router.push(`/skills/studio/${forked.skillId}`);
    } catch (err) {
      setSaveState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    } finally {
      setForking(false);
    }
  }, [skillId, router, t]);

  // A backend read-only error still carries the technical “fork” hint in its
  // detail, so this keeps surfacing the Fork action without re-deriving policy.
  const saveBlockedAsReadOnly = saveState.status === "error" && /fork/i.test(saveState.message);
  const showForkButton = isPlatformOwned || saveBlockedAsReadOnly;

  if (loadingSkill) {
    return <div className="page-container" role="status"><p className="skeleton p-6 text-sm text-muted-foreground">{t("studio.loadingSkill")}</p></div>;
  }
  if (loadError) {
    return (
      <main className="page-container p-6">
        <p className="notice notice--danger" role="alert">{t("studio.loadFailed", { error: loadError })}</p>
      </main>
    );
  }

  return (
    <SkillStudioShell
      draft={draft}
      isNew={isNew}
      isDirty={isDirty}
      isSaving={saveState.status === "saving" || forking}
      onSave={() => void handleSave()}
      onCancel={handleCancel}
    >
      {isPlatformOwned && (
        <div className="notice notice--info mb-4 block">
          {t("studio.platformSkillPrefix")} {" "}
          <span className="font-medium text-foreground">{t("studio.platformSkill")}</span>. {" "}
          {t("studio.platformSkillSuffix")}
        </div>
      )}
      {saveState.status === "ok" && <div role="status" className="notice notice--success mb-4">{saveState.message}</div>}
      {saveState.status === "error" && <div role="alert" className="notice notice--danger mb-4">{saveState.message}</div>}
      {showForkButton && (
        <div className="surface-sunken mb-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-xs">
          <span className="text-muted-foreground">{t("studio.platformSkillSuffix")}</span>
          <button type="button" onClick={() => void handleFork()} disabled={forking} className="button-secondary px-3 py-1.5 font-medium disabled:opacity-50">{forking ? t("studio.forking") : t("studio.fork")}</button>
        </div>
      )}
      <StudioBuilderForm draft={draft} setDraft={setDraft} isNew={isNew} />
    </SkillStudioShell>
  );
}

async function safeErrorDetail(res: Response): Promise<string | null> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (data.detail) return JSON.stringify(data.detail);
  } catch {
    // non-JSON body — no detail
  }
  return null;
}
