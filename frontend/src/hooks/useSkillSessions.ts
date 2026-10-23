"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";
import { subscribeSessionsChanged } from "@/lib/sessionEvents";

export interface ChatSessionSummary {
  session_id: string;
  document_ids: string[];
  skill_id: string;
  owner_uid: string;
  title: string | null;
  turn_count: number;
  first_message_at: string;
  last_message_at: string;
  archived_at: string | null;
  is_owner: boolean;
  /** Friendly name of the agent this conversation was with. Null when the
   * skill can't be resolved — render no chip rather than a raw UUID. */
  skill_label?: string | null;
  /** v6.23.0 B5 — this conversation's stored messages are gone; opening it
   * shows "no longer available". Surfaced in the list so a user learns that
   * BEFORE clicking. All known cases predate the 2026-08-05 session-sweep fix. */
  transcript_lost?: boolean;
}

interface ListSessionsResponse {
  sessions: ChatSessionSummary[];
  next_cursor: string | null;
}

export interface SessionSearchFilters {
  query?: string;
  updatedAfter?: string;
  updatedBefore?: string;
}

interface UseSkillSessionsReturn {
  sessions: ChatSessionSummary[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
  nextCursor: string | null;
  loadMore: () => void;
  isLoadingMore: boolean;
}

/**
 * The caller's past conversations, newest first.
 *
 * Cross-skill by DEFAULT. Switching agent via the top bar starts a new session
 * on the new skill, so one sitting that moved between agents is split into one
 * session per skill. Scoping this list to the current skill therefore showed
 * the user only the fragment belonging to wherever they were standing — a real
 * 7-turn sitting across two agents read as "it didn't record my session"
 * (2026-08-05). Every row carries `skill_label` so the list can say which agent
 * each conversation was with.
 *
 * @param skillFilter Pass a skillId to narrow to one agent; null for all.
 */
export function useSkillSessions(skillFilter: string | null, search?: SessionSearchFilters): UseSkillSessionsReturn {
  const searchEnabled = search !== undefined;
  const queryText = search?.query?.trim() ?? "";
  const updatedAfter = search?.updatedAfter ?? "";
  const updatedBefore = search?.updatedBefore ?? "";
  const scope = JSON.stringify([skillFilter, searchEnabled, queryText, updatedAfter, updatedBefore]);
  const [stateScope, setStateScope] = useState(scope);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);
  const busyRef = useRef(false);
  const cursorRef = useRef<string | null>(null);
  const consumedRef = useRef(new Set<string>());

  const request = useCallback((cursor: string | null) => {
    if (cursor !== null && (busyRef.current || consumedRef.current.has(cursor))) return;
    abortRef.current?.abort();
    const generation = ++generationRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    busyRef.current = true;
    const isCurrent = () => generation === generationRef.current && !controller.signal.aborted;

    setIsLoading(cursor === null);
    setIsLoadingMore(cursor !== null);
    setError(null);

    const params = [
      skillFilter ? `skill_id=${encodeURIComponent(skillFilter)}` : "",
      queryText ? `q=${encodeURIComponent(queryText)}` : "",
      updatedAfter ? `updated_after=${encodeURIComponent(updatedAfter)}` : "",
      updatedBefore ? `updated_before=${encodeURIComponent(updatedBefore)}` : "",
      cursor === null ? "" : `cursor=${encodeURIComponent(cursor)}`,
    ].filter(Boolean).join("&");
    fetchWithAuth(`/api/proxy/api/sessions${searchEnabled ? "/search" : ""}${params ? `?${params}` : ""}`, {
      signal: controller.signal,
    })
      .then((res) => {
        if (!isCurrent()) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<ListSessionsResponse>;
      })
      .then((data) => {
        if (!isCurrent() || !data) return;
        if (cursor === null) consumedRef.current.clear();
        else consumedRef.current.add(cursor);
        const next = data.next_cursor ?? null;
        cursorRef.current = next !== null && consumedRef.current.has(next) ? null : next;
        setNextCursor(cursorRef.current);
        setSessions((previous) => {
          if (!isCurrent()) return previous;
          const rows = cursor === null ? data.sessions : [...previous, ...data.sessions];
          const seen = new Set<string>();
          return rows.filter((row) => {
            if (seen.has(row.session_id)) return false;
            seen.add(row.session_id);
            return true;
          });
        });
      })
      .catch(() => {
        if (isCurrent()) setError("Failed to load sessions");
      })
      .finally(() => {
        if (!isCurrent()) return;
        busyRef.current = false;
        setIsLoading(false);
        setIsLoadingMore(false);
      });
  }, [skillFilter, searchEnabled, queryText, updatedAfter, updatedBefore]);

  const fetch_ = useCallback(() => request(null), [request]);
  const loadMore = useCallback(() => {
    if (cursorRef.current !== null) request(cursorRef.current);
  }, [request]);

  useEffect(() => {
    setStateScope(scope);
    setSessions([]);
    setNextCursor(null);
    cursorRef.current = null;
    consumedRef.current.clear();
    fetch_();
    return () => {
      abortRef.current?.abort();
      busyRef.current = false;
    };
  }, [fetch_, scope]);

  useEffect(() => {
    const onFocus = () => fetch_();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [fetch_]);

  // Cross-panel sync: when ANY session list (skill-level or per-document)
  // mutates, both hooks refetch. See lib/sessionEvents.ts.
  useEffect(() => subscribeSessionsChanged(fetch_), [fetch_]);

  const current = stateScope === scope;
  return { sessions: current ? sessions : [], isLoading: !current || isLoading,
    error: current ? error : null, refetch: fetch_, nextCursor: current ? nextCursor : null,
    loadMore, isLoadingMore: current && isLoadingMore };
}
