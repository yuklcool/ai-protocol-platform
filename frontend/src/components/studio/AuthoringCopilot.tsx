// Skill Studio — authoring copilot panel.

"use client";

import { Check, Pencil, X } from "lucide-react";
import { SendIcon } from "@/components/icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { useSkillAgent } from "@/hooks/useSkillAgent";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";
import {
  parseProposals,
  type Proposal,
} from "@/components/studio/applyProposal";

interface AuthoringCopilotProps {
  skillId: string;
  onApplyProposal: (proposal: Proposal) => void;
}

interface ProposalCard {
  key: string;
  proposal: Proposal;
}

export function threadStorageKey(skillId: string): string {
  return `studio-copilot-thread:${skillId}`;
}

function cardKey(messageId: string, index: number, p: Proposal): string {
  return `${messageId}:${index}:${p.kind}`;
}

export function AuthoringCopilot({ skillId, onApplyProposal }: AuthoringCopilotProps) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateSkillStudio>[1]) => translateSkillStudio(locale, key);
  const { sessionId, messages, sendMessage, isLoading, error, clearError } = useSkillAgent();
  const [draft, setDraft] = useState("");
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !sessionId) return;
    try {
      window.localStorage?.setItem(threadStorageKey(skillId), sessionId);
    } catch {
      // Thread persistence is optional.
    }
  }, [skillId, sessionId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    }
  }, [messages]);

  const cards: ProposalCard[] = useMemo(() => {
    const acc: ProposalCard[] = [];
    for (const m of messages) {
      if (m.role !== "assistant") continue;
      const proposals = parseProposals(m.content);
      proposals.forEach((p, i) => {
        const key = cardKey(m.id, i, p);
        if (dismissed.has(key)) return;
        acc.push({ key, proposal: p });
      });
    }
    return acc;
  }, [messages, dismissed]);

  const handleSend = useCallback(() => {
    const text = draft.trim();
    if (!text || isLoading) return;
    setDraft("");
    void sendMessage(text);
  }, [draft, isLoading, sendMessage]);

  const handleDismiss = useCallback((key: string) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  }, []);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{t("copilot.title")}</h2>
        <p className="text-xs text-muted-foreground">{t("copilot.description")}</p>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
        {messages.length === 0 && !isLoading && (
          <p className="text-sm text-muted-foreground">{t("copilot.empty")}</p>
        )}

        {messages.map((m) => (
          <MessageRow key={m.id} role={m.role} content={m.content} />
        ))}

        {isLoading && (
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {t("copilot.thinking")}
          </p>
        )}

        {cards.length > 0 && (
          <div className="space-y-2 pt-2" data-testid="proposal-cards">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("copilot.proposals")}
            </p>
            {cards.map((c) => (
              <ProposalCardView
                key={c.key}
                cardKey={c.key}
                proposal={c.proposal}
                onApply={onApplyProposal}
                onDismiss={handleDismiss}
              />
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="border-t border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive">
          <span>{error.message}</span>
          <button type="button" onClick={clearError} className="ml-2 underline">
            {t("copilot.dismissError")}
          </button>
        </div>
      )}

      <form
        className="flex gap-2 border-t p-3"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("copilot.placeholder")}
          aria-label={t("copilot.inputAria")}
          className="flex-1 rounded-md border px-3 py-2 text-sm"
          disabled={isLoading}
        />
        <button
          type="submit"
          className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
          disabled={!draft.trim() || isLoading}
        >
          <SendIcon className="h-4 w-4" />
          {t("copilot.send")}
        </button>
      </form>
    </div>
  );
}

function MessageRow({ role, content }: { role: "user" | "assistant"; content: string }) {
  const { locale } = useI18n();
  const isUser = role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          "max-w-[85%] whitespace-pre-wrap rounded-md border px-3 py-2 text-sm " +
          (isUser ? "bg-primary/10" : "bg-muted/40")
        }
      >
        {content || <span className="text-muted-foreground">{translateSkillStudio(locale, "copilot.noText")}</span>}
      </div>
    </div>
  );
}

function ProposalCardView({
  cardKey,
  proposal,
  onApply,
  onDismiss,
}: {
  cardKey: string;
  proposal: Proposal;
  onApply: (p: Proposal) => void;
  onDismiss: (key: string) => void;
}) {
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translateSkillStudio>[1],
    params: Record<string, string | number> = {},
  ) => translateSkillStudio(locale, key, params);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(() => proposalToEditText(proposal));
  const [editError, setEditError] = useState<string | null>(null);

  const usesSpec = proposal.spec !== undefined;

  const handleApply = () => {
    if (!editing) {
      onApply(proposal);
      return;
    }
    const edited = editTextToProposal(proposal, editText);
    if (edited === null) {
      setEditError(usesSpec ? t("copilot.invalidSpec") : t("copilot.invalidValue"));
      return;
    }
    setEditError(null);
    onApply(edited);
    setEditing(false);
  };

  return (
    <div className="rounded-md border p-3 text-sm" data-testid="proposal-card">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{proposal.label}</p>
          <p className="text-xs text-muted-foreground">{proposal.kind}</p>
        </div>
      </div>

      {editing ? (
        <div className="mt-2 space-y-1">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            aria-label={t("copilot.editAria", { label: proposal.label })}
            rows={usesSpec ? 4 : 2}
            className="w-full rounded border px-2 py-1 font-mono text-xs"
          />
          {editError && <p className="text-xs text-destructive">{editError}</p>}
        </div>
      ) : (
        <ProposalPreview proposal={proposal} />
      )}

      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={handleApply}
          className="inline-flex items-center gap-1 rounded border bg-primary px-2 py-1 text-xs text-primary-foreground"
        >
          <Check className="h-3.5 w-3.5" aria-hidden />
          {t("copilot.apply")}
        </button>
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs"
        >
          <Pencil className="h-3.5 w-3.5" aria-hidden />
          {editing ? t("copilot.cancelEdit") : t("copilot.edit")}
        </button>
        <button
          type="button"
          onClick={() => onDismiss(cardKey)}
          className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
          {t("copilot.dismiss")}
        </button>
      </div>
    </div>
  );
}

function ProposalPreview({ proposal }: { proposal: Proposal }) {
  const text =
    proposal.spec !== undefined
      ? JSON.stringify(proposal.spec, null, 2)
      : Array.isArray(proposal.value)
        ? proposal.value.join(", ")
        : (proposal.value ?? "");
  if (!text) return null;
  return (
    <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted/40 px-2 py-1 text-xs">
      {text}
    </pre>
  );
}

function proposalToEditText(p: Proposal): string {
  if (p.spec !== undefined) return JSON.stringify(p.spec, null, 2);
  if (Array.isArray(p.value)) return p.value.join(", ");
  return p.value ?? "";
}

function editTextToProposal(p: Proposal, text: string): Proposal | null {
  if (p.spec !== undefined) {
    try {
      const spec = JSON.parse(text);
      if (!spec || typeof spec !== "object" || Array.isArray(spec)) return null;
      return { ...p, spec: spec as Record<string, unknown> };
    } catch {
      return null;
    }
  }
  if (Array.isArray(p.value)) {
    const arr = text
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return { ...p, value: arr };
  }
  return { ...p, value: text };
}
