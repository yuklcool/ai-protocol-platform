"use client";

/** Browser-side session helpers for the built-in self-host JWT provider.
 *
 * Tokens live in sessionStorage rather than a long-lived cookie/localStorage.
 * This keeps the first baseline simple: closing the tab drops the bearer token,
 * while backend PostgreSQL remains the authority for user/domain/role data.
 */

export const LOCAL_JWT_SESSION_STORAGE_KEY = "aitana:local_jwt_session";
export const LOCAL_JWT_AUTH_CHANGED_EVENT = "aitana:local-jwt-auth-changed";

export interface LocalJwtUser {
  uid: string;
  email: string;
  domain: string;
  groupTags: string[];
  authMode: string;
}

export interface LocalJwtSession {
  token: string;
  expiresAt: number;
  user: LocalJwtUser;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: LocalJwtUser;
}

export function isLocalJwtAuthMode(): boolean {
  const raw = (process.env.NEXT_PUBLIC_AUTH_MODE || "").trim().toLowerCase();
  return raw === "local-jwt" || raw === "local_jwt" || raw === "jwt";
}

function notifyAuthChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(LOCAL_JWT_AUTH_CHANGED_EVENT));
}

export function readLocalJwtSession(): LocalJwtSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(LOCAL_JWT_SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as LocalJwtSession;
    if (
      typeof parsed.token !== "string" ||
      typeof parsed.expiresAt !== "number" ||
      !parsed.user ||
      typeof parsed.user.uid !== "string" ||
      typeof parsed.user.email !== "string"
    ) {
      clearLocalJwtSession();
      return null;
    }
    if (parsed.expiresAt <= Date.now()) {
      clearLocalJwtSession();
      return null;
    }
    return parsed;
  } catch {
    clearLocalJwtSession();
    return null;
  }
}

export function writeLocalJwtSession(session: LocalJwtSession): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(LOCAL_JWT_SESSION_STORAGE_KEY, JSON.stringify(session));
  notifyAuthChanged();
}

export function clearLocalJwtSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(LOCAL_JWT_SESSION_STORAGE_KEY);
  notifyAuthChanged();
}

export function getLocalJwtToken(): string | null {
  return readLocalJwtSession()?.token ?? null;
}

export async function loginWithLocalJwt(email: string, password: string): Promise<LocalJwtSession> {
  const response = await fetch("/api/proxy/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = "Sign-in failed";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) detail = body.detail;
    } catch {
      // Preserve the generic message for non-JSON upstream failures.
    }
    throw new Error(detail);
  }

  const payload = (await response.json()) as LoginResponse;
  if (!payload.access_token || !payload.user?.uid || !payload.expires_in) {
    throw new Error("Invalid sign-in response")
  }

  const session: LocalJwtSession = {
    token: payload.access_token,
    expiresAt: Date.now() + payload.expires_in * 1000,
    user: payload.user,
  };
  writeLocalJwtSession(session);
  return session;
}

/** Re-resolve identity through the backend so browser-stored role metadata is
 * never treated as authoritative. The backend reloads the user from PostgreSQL
 * before returning whoami. */
export async function validateLocalJwtSession(
  session: LocalJwtSession,
): Promise<LocalJwtSession | null> {
  const response = await fetch("/api/proxy/api/auth/whoami", {
    headers: { Authorization: `Bearer ${session.token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) clearLocalJwtSession();
    return null;
  }
  const user = (await response.json()) as LocalJwtUser;
  const refreshed = { ...session, user };
  writeLocalJwtSession(refreshed);
  return refreshed;
}

export function subscribeToLocalJwtToken(
  callback: (token: string | null) => void,
): () => void {
  if (typeof window === "undefined") {
    callback(null);
    return () => {};
  }
  const emit = () => callback(getLocalJwtToken());
  emit();
  window.addEventListener(LOCAL_JWT_AUTH_CHANGED_EVENT, emit);
  return () => window.removeEventListener(LOCAL_JWT_AUTH_CHANGED_EVENT, emit);
}
