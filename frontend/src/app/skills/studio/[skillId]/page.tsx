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
import { AGUIProvider } from "@/providers/AGUIProvider";
import { SignInRequired } from "@/components/chat/SignInRequired";
import {
  AuthoringCopilot,
  threadStorageKey,
} from "@/components/studio/AuthoringCopilot";
import { StudioBuilderForm } from "@/components/studio/StudioBuilderForm";
import { SkillStudioShell } from "@/components/agent/AgentStudioShell";
import {
  applyProposal,
  type Proposal,
  type StudioDraft,
} from "@/components/studio/applyProposal";
import type { Skill } from "@/types/skill";
import { randomGlyphAvatar } from "@/lib/defaultAvatars";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";

const STUDIO_ENABLED = process.env.NEXT_PUBLIC_ENABLE_SKILL_STUDIO === "true";

/** The copilot always talks to this platform skill (seeded backend M3). */
const AUTHORING_SKILL_ID = "skill-authoring-assistant";

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
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">
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

  // Seed the copilot thread from localStorage so a reload resumes the same
  // conversation for this edited skill.
  const seededThreadId = useMemo(() => {
    if (typeof window === "undefined") return undefined;
    return window.localStorage.getItem(threadStorageKey(skillId)) ?? undefined;
  }, [skillId]);

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

  const onApplyProposal = useCallback((proposal: Proposal) => {
    setDraft((prev) => applyProposal(prev, proposal));
  }, []);

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
        message: err instanceof Error ? err.message : String(err),
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
    return <div className="p-6 text-sm text-muted-foreground">{t("studio.loadingSkill")}</div>;
  }
  if (loadError) {
    return (
      <main className="p-6">
        <p className="text-sm text-destructive">{t("studio.loadFailed", { error: loadError })}</p>
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
        <div className="mb-4 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
          {t("studio.platformSkillPrefix")} {" "}
          <span className="font-medium text-foreground">{t("studio.platformSkill")}</span>. {" "}
          {t("studio.platformSkillSuffix")}
        </div>
      )}
      {saveState.status === "ok" && <div className="mb-4 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-700">{saveState.message}</div>}
      {saveState.status === "error" && <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">{saveState.message}</div>}
      {showForkButton && (
        <div className="mb-4 flex items-center justify-between rounded-md border bg-card px-3 py-2 text-xs">
          <span className="text-muted-foreground">{t("studio.platformSkillSuffix")}</span>
          <button type="button" onClick={() => void handleFork()} disabled={forking} className="rounded-md border px-2.5 py-1.5 font-medium hover:bg-muted disabled:opacity-50">{forking ? t("studio.forking") : t("studio.fork")}</button>
        </div>
      )}
      <StudioBuilderForm draft={draft} setDraft={setDraft} isNew={isNew} />
      <div className="mt-6 hidden border-t pt-6 xl:block">
        <AGUIProvider agentId={AUTHORING_SKILL_ID} skillId={AUTHORING_SKILL_ID} sessionId={seededThreadId}>
          <AuthoringCopilot skillId={skillId} onApplyProposal={onApplyProposal} />
        </AGUIProvider>
      </div>
    </SkillStudioShell>
  );
}

function emptyDraft(): StudioDraft {
  return {
    name: "",
    displayName: "",
    description: "",
    instructions: "",
    skillMetadata: { model: "smart", tools: [], subSkills: [], toolConfigs: {} },
    persona: { avatar: randomGlyphAvatar(), interactionStyle: "concise", voice: {} },
    welcome: {},
  };
}

function skillToDraft(s: Skill): StudioDraft {
  return {
    skillId: s.skillId,
    ownerId: s.ownerId,
    name: s.name,
    displayName: s.displayName,
    description: s.description,
    instructions: s.instructions,
    avatar: s.avatar,
    skillMetadata: {
      model: s.skillMetadata?.model,
      tools: s.skillMetadata?.tools ?? [],
      subSkills: s.skillMetadata?.subSkills ?? [],
      toolConfigs: s.skillMetadata?.toolConfigs ?? {},
      ...(s.skillMetadata?.delegation ? { delegation: s.skillMetadata.delegation } : {}),
      ...(s.skillMetadata?.category ? { category: s.skillMetadata.category } : {}),
      ...(s.skillMetadata?.enableConfirmation === false ? { enableConfirmation: false } : {}),
    },
    persona: s.persona ?? { interactionStyle: "concise" },
    welcome: s.welcome ?? {},
    accessControl: s.accessControl as unknown as Record<string, unknown>,
  };
}

function buildSaveBody(draft: StudioDraft, isNew: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    description: draft.description ?? "",
    instructions: draft.instructions ?? "",
    displayName: draft.displayName ?? "",
    skillMetadata: draft.skillMetadata ?? {},
    persona: draft.persona ?? {},
    welcome: draft.welcome ?? {},
    accessControl: draft.accessControl ?? { type: "private" },
  };
  if (isNew) body.name = draft.name ?? "";
  return body;
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
