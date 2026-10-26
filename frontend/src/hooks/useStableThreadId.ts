"use client";

import { useState } from "react";
import { v4 as createUuid } from "uuid";

/**
 * Stable threadId for AGUIProvider that survives the URL-writeback after
 * the first message of a fresh chat.
 *
 * Without this, the chat page passes ``urlSessionId ?? undefined`` straight
 * to AGUIProvider, whose ``useMemo([skillId, token, sessionId])`` rebuilds
 * the HttpAgent the moment the URL-writeback effect rewrites
 * ``?session=<id>`` after the first turn. The rebuild destroys the
 * in-memory ``agent.messages`` list — F1's agent-identity guard correctly
 * yields, but the user briefly sees an empty live area until
 * ``useSessionMessages`` GET populates ``initialMessages``. That's the
 * visible flicker described in
 * docs/archive/design/v6.1.0/chat-history-deep-fixes-2.md as Bug A'.
 *
 * Lifecycle:
 * - Initial mount, no URL session: mint a fresh UUID.
 * - Initial mount, URL has ``?session=<id>``: adopt that id.
 * - URL gains ``?session=<id>`` and ``id`` matches the current threadId
 *   (our own writeback effect): no change.
 * - URL changes to a different ``?session=<other>`` (user clicked another
 *   thread): adopt the new id; AGUIProvider rebuilds intentionally.
 * - URL clears ``?session=`` (user clicked "+ New conversation"): mint a
 *   fresh UUID; AGUIProvider rebuilds intentionally.
 */
export function useStableThreadId(urlSessionId: string | null): string {
  const [state, setState] = useState(() => ({
    urlSessionId,
    threadId: urlSessionId ?? createUuid(),
  }));
  if (state.urlSessionId !== urlSessionId) {
    // Update before children commit. An effect leaves one render with the
    // previous agent, whose URL-writeback can reopen the chat just cleared.
    // Writing our own id to the URL keeps the provider key unchanged.
    const threadId = urlSessionId ?? createUuid();
    setState({ urlSessionId, threadId });
    return threadId;
  }
  return state.threadId;
}
