// Chat-placement A2UI surfaces rendered inline in the chat thread.
// Backend-emitted titles and A2UI content remain authoritative; only the
// frontend fallback/submitted labels are localized here.

"use client";

import { A2UISurfaceMount } from "@/components/protocols/A2UISurfaceMount";
import { useArtifacts } from "@/providers/SurfaceRegistry";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

export const ELICITATION_FORM_KIND = "obligation-elicitation-form";

export interface ChatPlacementFormProps {
  surfaceId: string;
  submitted: boolean;
  sessionId: string | null;
  skillId: string;
  isConfirm?: boolean;
  /** Backend-provided, friendly AI-authored title. */
  title?: string;
  reusable?: boolean;
  onStop?: () => void;
}

export function ChatPlacementForm({
  surfaceId,
  submitted,
  sessionId,
  skillId,
  isConfirm,
  title,
  reusable = false,
  onStop,
}: ChatPlacementFormProps) {
  const { locale } = useI18n();
  const headerLabel = submitted
    ? translateChat(locale, "placement.submitted")
    : title || translateChat(locale, isConfirm ? "placement.confirm" : "placement.actionNeeded");

  return (
    <div
      className={
        "w-full max-w-2xl overflow-hidden glass-panel shadow-sm " +
        (submitted ? "border-dashed bg-muted/10" : "border-l-2 border-l-primary/60 bg-card")
      }
      data-chat-form={surfaceId}
      data-submitted={submitted || undefined}
    >
      <div
        className={
          "flex items-center gap-1.5 border-b px-4 py-2 " +
          (submitted
            ? "bg-muted/40 text-xs font-medium text-muted-foreground"
            : "text-sm font-semibold text-foreground")
        }
      >
        {submitted && (
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M20 6 9 17l-5-5"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
        {headerLabel}
      </div>
      <div className={submitted ? "pointer-events-none opacity-75" : undefined}>
        <A2UISurfaceMount
          key={`${sessionId}:${surfaceId}`}
          surfaceId={surfaceId}
          sessionId={sessionId}
          skillId={skillId}
          triggerOnAction={!submitted}
          freezeAfterAction={!reusable}
          readOnly={submitted}
          onStop={onStop}
          className={"chat-a2ui-form px-4 py-3" + (isConfirm ? " chat-a2ui-form--confirm" : "")}
        />
      </div>
    </div>
  );
}

export interface ChatSurfaceItem {
  surfaceId: string;
  createdAt: number;
  submitted: boolean;
  isConfirm: boolean;
  title?: string;
  replayed: boolean;
  reusable?: boolean;
}

export function useChatSurfaces(): ChatSurfaceItem[] {
  const chat = useArtifacts().filter((a) => a.placement === "chat");
  const lastId = chat[chat.length - 1]?.surfaceId;
  return chat.map((a) => ({
    surfaceId: a.surfaceId,
    createdAt: a.createdAt,
    submitted:
      (Boolean(a.replayed) && a.kind !== "a2ui") || (a.kind === ELICITATION_FORM_KIND && a.surfaceId !== lastId),
    isConfirm: a.elicitationKind === "confirm",
    title: a.title,
    replayed: Boolean(a.replayed),
    reusable: a.kind === "a2ui",
  }));
}
