"use client";

import { useState } from "react";
import { useDocumentSessions } from "@/hooks/useDocumentSessions";
import type { ChatSessionSummary } from "@/hooks/useDocumentSessions";
import { fetchWithAuth } from "@/lib/apiClient";
import { notifySessionsChanged } from "@/lib/sessionEvents";
import { useI18n } from "@/contexts/I18nContext";
import type { Locale } from "@/lib/i18n";
import { translateChat } from "@/lib/i18n/chat";

export interface DocumentHistoryPanelProps {
  documentId: string;
  activeSessionId: string | null;
  currentUserUid: string;
  onSelectSession: (sessionId: string, ownerUid: string) => void;
  onNewSession: () => void;
  onDeleteActive?: () => void;
}

function relativeTime(iso: string, locale: Locale): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return translateChat(locale, "time.minutesAgo", { count: mins });
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return translateChat(locale, "time.hoursAgo", { count: hrs });
  return translateChat(locale, "time.daysAgo", { count: Math.floor(hrs / 24) });
}

interface SessionRowProps {
  session: ChatSessionSummary;
  isActive: boolean;
  isOwner: boolean;
  onClick: () => void;
  onRename: (newTitle: string) => Promise<void>;
  onDelete?: () => void;
}

function SessionRow({ session, isActive, isOwner, onClick, onRename, onDelete }: SessionRowProps) {
  const { locale } = useI18n();
  const initialTitle = session.title ?? translateChat(locale, "history.untitled");
  const time = relativeTime(session.last_message_at, locale);
  const turns = translateChat(
    locale,
    session.turn_count === 1 ? "history.turnOne" : "history.turnMany",
    { count: session.turn_count },
  );
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(initialTitle);
  const [saving, setSaving] = useState(false);

  async function commit() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === initialTitle) {
      setIsEditing(false);
      setDraft(initialTitle);
      return;
    }
    setSaving(true);
    try {
      await onRename(trimmed);
      setIsEditing(false);
    } catch {
      setDraft(initialTitle);
      setIsEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (isEditing) {
    return (
      <div
        className={[
          "w-full px-3 py-2 rounded text-sm",
          isActive ? "bg-blue-50 border border-blue-200" : "bg-gray-50",
        ].join(" ")}
      >
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void commit();
            } else if (e.key === "Escape") {
              setDraft(initialTitle);
              setIsEditing(false);
            }
          }}
          disabled={saving}
          className="w-full bg-transparent font-medium text-gray-900 outline-none"
          aria-label={translateChat(locale, "history.renameAria")}
        />
        <div className="text-xs text-gray-400 mt-0.5">
          {time} · {turns}
        </div>
      </div>
    );
  }

  return (
    <div
      className={[
        "group flex w-full items-center gap-1 px-3 py-2 rounded text-sm transition-colors",
        isActive
          ? "bg-blue-50 border border-blue-200 text-blue-900"
          : "hover:bg-gray-50 text-gray-700",
      ].join(" ")}
    >
      <button onClick={onClick} className="min-w-0 flex-1 text-left">
        <div className="font-medium truncate">{initialTitle}</div>
        <div className="text-xs text-gray-400 mt-0.5">
          {time} · {turns}
        </div>
      </button>
      {isOwner && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setDraft(initialTitle);
            setIsEditing(true);
          }}
          aria-label={translateChat(locale, "history.renameAriaWithTitle", { title: initialTitle })}
          title={translateChat(locale, "history.rename")}
          className="shrink-0 rounded p-1 text-gray-400 opacity-0 hover:bg-gray-200 hover:text-gray-700 group-hover:opacity-100"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M11 2l3 3-7 7H4v-3l7-7z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      {isOwner && onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label={translateChat(locale, "history.deleteAriaWithTitle", { title: initialTitle })}
          title={translateChat(locale, "history.delete")}
          className="shrink-0 rounded p-1 text-gray-400 opacity-0 hover:bg-red-100 hover:text-red-600 group-hover:opacity-100"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M3 4h10M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4M7 4V3a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v1" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </div>
  );
}

async function renameSession(sessionId: string, title: string): Promise<void> {
  const res = await fetchWithAuth(`/api/proxy/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetchWithAuth(`/api/proxy/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export default function DocumentHistoryPanel({
  documentId,
  activeSessionId,
  currentUserUid,
  onSelectSession,
  onNewSession,
  onDeleteActive,
}: DocumentHistoryPanelProps) {
  const { locale } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const { sessions, isLoading, error } = useDocumentSessions(documentId);

  const mine = sessions.filter((s) => s.owner_uid === currentUserUid);
  const team = sessions.filter((s) => s.owner_uid !== currentUserUid);
  const totalCount = sessions.length;

  async function handleRename(sessionId: string, title: string): Promise<void> {
    await renameSession(sessionId, title);
    notifySessionsChanged();
  }

  async function handleDelete(sessionId: string): Promise<void> {
    if (!window.confirm(translateChat(locale, "history.deleteConfirm"))) return;
    try {
      await deleteSession(sessionId);
      notifySessionsChanged({ deletedSessionId: sessionId });
      if (sessionId === activeSessionId) onDeleteActive?.();
    } catch {
      notifySessionsChanged();
    }
  }

  return (
    <div className="border-b border-gray-200">
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        aria-expanded={isOpen}
      >
        <span className="flex items-center gap-2">
          {translateChat(locale, "history.conversations")}
          {totalCount > 0 && (
            <span
              className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600"
              aria-label={translateChat(locale, "history.conversationCount", { count: totalCount })}
            >
              {totalCount}
            </span>
          )}
        </span>
        <span className="text-gray-400">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        <div className="max-h-[25vh] overflow-y-auto px-3 pb-3 space-y-3">
          {isLoading && (
            <p className="text-xs text-gray-400 px-1">{translateChat(locale, "history.loading")}</p>
          )}
          {error && <p className="text-xs text-red-500 px-1">{error}</p>}

          {!error && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide px-1 mb-1">
                {translateChat(locale, "history.mine")}
              </p>
              {mine.length === 0 && !isLoading && (
                <p className="text-xs text-gray-400 px-1">{translateChat(locale, "history.none")}</p>
              )}
              <div className="space-y-1">
                {mine.map((s) => (
                  <SessionRow
                    key={s.session_id}
                    session={s}
                    isActive={s.session_id === activeSessionId}
                    isOwner={true}
                    onClick={() => onSelectSession(s.session_id, s.owner_uid)}
                    onRename={(t) => handleRename(s.session_id, t)}
                    onDelete={() => void handleDelete(s.session_id)}
                  />
                ))}
              </div>
            </div>
          )}

          {!error && team.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide px-1 mb-1">
                {translateChat(locale, "history.team")}
              </p>
              <div className="space-y-1">
                {team.map((s) => (
                  <SessionRow
                    key={s.session_id}
                    session={s}
                    isOwner={false}
                    onRename={async () => {}}
                    isActive={s.session_id === activeSessionId}
                    onClick={() => onSelectSession(s.session_id, s.owner_uid)}
                  />
                ))}
              </div>
            </div>
          )}

          <button
            onClick={onNewSession}
            className="w-full text-left px-3 py-2 rounded text-sm text-blue-600 hover:bg-blue-50 transition-colors"
          >
            {translateChat(locale, "history.newConversation")}
          </button>
        </div>
      )}
    </div>
  );
}
