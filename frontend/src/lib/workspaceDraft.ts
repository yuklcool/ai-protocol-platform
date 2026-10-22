/** One-shot, tab-scoped handoff from Workspace to a fresh chat composer.
 * No message, session or run is created until the user explicitly sends.
 * Owner scoping and TTL prevent stale drafts from being shown after an account switch.
 */
const STORAGE_KEY = "ai-protocol-platform:workspace-draft:v1";
const TTL_MS = 5 * 60 * 1000;
export const WORKSPACE_DRAFT_LIMIT = 4000;

type PendingDraft = {
  ownerUid: string;
  text: string;
  createdAt: number;
};

export function stageWorkspaceDraft(text: string, ownerUid: string): boolean {
  const value = text.trim();
  if (!ownerUid || !value || value.length > WORKSPACE_DRAFT_LIMIT) return false;
  try {
    const payload: PendingDraft = { ownerUid, text: value, createdAt: Date.now() };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

/** Read once, removing the draft even if corrupt, expired or owned by another UID. */
export function consumeWorkspaceDraft(ownerUid: string): string | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    window.sessionStorage.removeItem(STORAGE_KEY);
    if (!raw || !ownerUid) return null;
    const payload: unknown = JSON.parse(raw);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
    const data = payload as Partial<PendingDraft>;
    const age = Date.now() - (data.createdAt ?? NaN);
    if (data.ownerUid !== ownerUid || typeof data.text !== "string" ||
        !data.text.trim() || data.text.length > WORKSPACE_DRAFT_LIMIT ||
        !Number.isFinite(age) || age < 0 || age > TTL_MS) return null;
    return data.text;
  } catch {
    return null;
  }
}
