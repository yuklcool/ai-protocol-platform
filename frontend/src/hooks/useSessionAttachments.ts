"use client";

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { DocTabData } from "@/components/doc-browser/DocTab";
import type { User } from "@/lib/firebase";
import { DOCUMENTS_CHANGED, documentRequest } from "@/lib/documents";

export function useSessionAttachments(sessionId: string | null, skillId: string, user: User) {
  const [state, setState] = useState<{ key: string | null; owner: User | null; tabs: DocTabData[] }>({ key: null, owner: null, tabs: [] });
  const [loaded, setLoaded] = useState<{key: string; owner: User} | null>(null);
  const loadedKey = loaded?.owner === user ? loaded.key : null;
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  const ticket = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const queued = useRef("");
  const lastRetry = useRef(0);
  const tabs = state.key === sessionId && state.owner === user ? state.tabs : [];
  const latest = useRef(tabs);
  latest.current = tabs;
  const choices = JSON.stringify(tabs.map(({ id, included }) => ({ id, included })));
  const setTabs: Dispatch<SetStateAction<DocTabData[]>> = useCallback((next) => {
    setState((previous) => {
      const current = previous.key === sessionId && previous.owner === user ? previous.tabs : [];
      return { key: sessionId, owner: user, tabs: typeof next === "function" ? next(current) : next };
    });
  }, [sessionId, user]);

  useEffect(() => {
    const version = ++generation.current;
    const controller = new AbortController();
    queue.current = Promise.resolve(); queued.current = "";
    setLoaded(null); setSaving(false); setError(null); setRetry(0);
    if (!sessionId) return;
    void (async () => {
      await documentRequest(`/sessions/${encodeURIComponent(sessionId)}/bootstrap`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ skill_id: skillId, agent_id: "root-agent" }),
      });
      const value = await documentRequest<{ documents: DocTabData[] }>(`/sessions/${encodeURIComponent(sessionId)}/documents`, { signal: controller.signal });
      if (version !== generation.current || controller.signal.aborted) return;
      queued.current = JSON.stringify(value.documents.map(({ id, included }) => ({ id, included })));
      lastRetry.current = 0;
      setState({ key: sessionId, owner: user, tabs: value.documents });
      setLoaded({key: sessionId, owner: user});
    })().catch((failure) => { if (!controller.signal.aborted && version === generation.current) setError(failure.message); });
    return () => { controller.abort(); generation.current = version + 1; };
  }, [sessionId, skillId, user, reload]);

  useEffect(() => {
    if (!sessionId || loadedKey !== sessionId || (choices === queued.current && retry === lastRetry.current)) return;
    const version = generation.current;
    queued.current = choices; lastRetry.current = retry;
    const currentTicket = ++ticket.current;
    setSaving(true); setError(null);
    queue.current = queue.current.catch(() => {}).then(async () => {
      if (version !== generation.current) return;
      await documentRequest(`/sessions/${encodeURIComponent(sessionId)}/documents`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ documents: JSON.parse(choices) }),
      });
    }).then(() => {
      if (version === generation.current && currentTicket === ticket.current) { setSaving(false); setError(null); }
    }).catch((failure) => {
      if (version === generation.current && currentTicket === ticket.current) { setSaving(false); setError(failure.message); }
    });
  }, [sessionId, loadedKey, choices, retry]);

  useEffect(() => {
    if (!sessionId || loadedKey !== sessionId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = async () => {
      const selected = latest.current;
      const values = await Promise.all(selected.map(async (tab) => {
        try {
          const row = await documentRequest<{ originalFilename: string; sourceFormat: string; parseStatus: DocTabData["parseStatus"]; parseError: string | null; sizeBytes?: number }>(`/documents/${encodeURIComponent(tab.id)}`, { signal: controller.signal });
          return { ...tab, filename: row.originalFilename, format: row.sourceFormat, parseStatus: row.parseStatus, parseError: row.parseError, sizeBytes: row.sizeBytes };
        } catch (failure) { return { ...tab, parseStatus: "failed" as const, parseError: (failure as Error).message }; }
      }));
      if (controller.signal.aborted) return;
      const byId = new Map(values.map((tab) => [tab.id, tab]));
      setTabs((current) => current.map((tab) => { const fresh = byId.get(tab.id); return fresh ? { ...tab, ...fresh, included: tab.included } : tab; }));
      if (values.some((tab) => tab.parseStatus === "pending")) timer = setTimeout(() => void refresh(), 2000);
    };
    const changed = () => { clearTimeout(timer); void refresh(); };
    window.addEventListener(DOCUMENTS_CHANGED, changed);
    window.addEventListener("focus", changed);
    if (latest.current.some((tab) => tab.parseStatus === "pending")) void refresh();
    return () => { controller.abort(); clearTimeout(timer); window.removeEventListener(DOCUMENTS_CHANGED, changed); window.removeEventListener("focus", changed); };
  }, [sessionId, loadedKey, setTabs]);
  return { tabs, setTabs, ready: loadedKey === sessionId && !!sessionId, saving, error, retrySave: () => loadedKey === sessionId ? setRetry((value) => value + 1) : setReload((value) => value + 1) };
}
