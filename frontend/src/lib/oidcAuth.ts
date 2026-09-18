"use client";

export const OIDC_SESSION_STORAGE_KEY = "aip:oidc_session";
export const OIDC_AUTH_CHANGED_EVENT = "aip:oidc-auth-changed";

export interface OidcUser {
  uid: string;
  email: string;
  domain: string;
  tenantId?: string;
  groupTags: string[];
  authMode: string;
}

export interface OidcSession {
  token: string;
  expiresAt: number;
  user: OidcUser;
}

interface OidcStartResponse {
  authorization_url: string;
  expires_in: number;
}

interface OidcCallbackResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  return_to: string;
  user: OidcUser;
}

export function isOidcAuthMode(): boolean {
  const raw = (process.env.NEXT_PUBLIC_AUTH_MODE || "").trim().toLowerCase();
  return raw === "oidc";
}

function notifyAuthChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(OIDC_AUTH_CHANGED_EVENT));
}

export function readOidcSession(): OidcSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(OIDC_SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as OidcSession;
    if (
      typeof parsed.token !== "string" ||
      typeof parsed.expiresAt !== "number" ||
      !parsed.user ||
      typeof parsed.user.uid !== "string" ||
      typeof parsed.user.email !== "string"
    ) {
      clearOidcSession();
      return null;
    }
    if (parsed.expiresAt <= Date.now()) {
      clearOidcSession();
      return null;
    }
    return parsed;
  } catch {
    clearOidcSession();
    return null;
  }
}

export function writeOidcSession(session: OidcSession): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(OIDC_SESSION_STORAGE_KEY, JSON.stringify(session));
  notifyAuthChanged();
}

export function clearOidcSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(OIDC_SESSION_STORAGE_KEY);
  notifyAuthChanged();
}

export function getOidcToken(): string | null {
  return readOidcSession()?.token ?? null;
}

function currentReturnTo(): string {
  if (typeof window === "undefined") return "/";
  return `${window.location.pathname}${window.location.search}${window.location.hash}` || "/";
}

export async function startOidcSignIn(returnTo = currentReturnTo()): Promise<void> {
  if (typeof window === "undefined") {
    throw new Error("OIDC sign-in requires a browser");
  }
  const response = await fetch(
    `/api/proxy/api/auth/oidc/start?return_to=${encodeURIComponent(returnTo)}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    let detail = "OIDC sign-in is unavailable";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) detail = body.detail;
    } catch {
      // Keep generic error for non-JSON upstream failures.
    }
    throw new Error(detail);
  }
  const payload = (await response.json()) as OidcStartResponse;
  if (!payload.authorization_url) {
    throw new Error("Invalid OIDC authorization response");
  }
  window.location.assign(payload.authorization_url);
}

export async function completeOidcSignIn(
  code: string,
  state: string,
): Promise<{ session: OidcSession; returnTo: string }> {
  const response = await fetch("/api/proxy/api/auth/oidc/callback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, state }),
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = "OIDC sign-in failed";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) detail = body.detail;
    } catch {
      // Keep generic error for non-JSON upstream failures.
    }
    throw new Error(detail);
  }

  const payload = (await response.json()) as OidcCallbackResponse;
  if (!payload.access_token || !payload.user?.uid || !payload.expires_in) {
    throw new Error("Invalid OIDC callback response");
  }
  const session: OidcSession = {
    token: payload.access_token,
    expiresAt: Date.now() + payload.expires_in * 1000,
    user: payload.user,
  };
  writeOidcSession(session);
  const returnTo =
    typeof payload.return_to === "string" &&
    payload.return_to.startsWith("/") &&
    !payload.return_to.startsWith("//") &&
    !payload.return_to.includes("\\")
      ? payload.return_to
      : "/";
  return { session, returnTo };
}

export async function validateOidcSession(
  session: OidcSession,
): Promise<OidcSession | null> {
  const response = await fetch("/api/proxy/api/auth/whoami", {
    headers: { Authorization: `Bearer ${session.token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) clearOidcSession();
    return null;
  }
  const user = (await response.json()) as OidcUser;
  const refreshed = { ...session, user };
  writeOidcSession(refreshed);
  return refreshed;
}

export function subscribeToOidcToken(
  callback: (token: string | null) => void,
): () => void {
  if (typeof window === "undefined") {
    callback(null);
    return () => {};
  }
  const emit = () => callback(getOidcToken());
  emit();
  window.addEventListener(OIDC_AUTH_CHANGED_EVENT, emit);
  return () => window.removeEventListener(OIDC_AUTH_CHANGED_EVENT, emit);
}
