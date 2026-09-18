import { type FirebaseApp, getApps, initializeApp } from "firebase/app";
import {
  type Auth,
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  onIdTokenChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut as fbSignOut,
  type User,
} from "firebase/auth";
import { type Firestore, getFirestore } from "firebase/firestore";
import {
  isAnonymousGroupAuthMode,
  readStoredGroupSession,
} from "@/lib/anonymousGroupAuth";
import {
  getLocalJwtToken,
  isLocalJwtAuthMode,
  subscribeToLocalJwtToken,
} from "@/lib/localJwtAuth";
import { isLocalMode, LOCAL_MODE_STUB_TOKEN } from "@/lib/localMode";
import {
  getOidcToken,
  isOidcAuthMode,
  subscribeToOidcToken,
} from "@/lib/oidcAuth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

let appInstance: FirebaseApp | null = null;
let authInstance: Auth | null = null;

function isConfigured(): boolean {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);
}

export function getFirebaseApp(): FirebaseApp | null {
  // Non-Firebase identity modes must never initialize the Firebase SDK merely
  // because unrelated public Firebase variables happen to be present.
  if (isOidcAuthMode() || isLocalJwtAuthMode() || isLocalMode()) return null;
  if (!isConfigured()) return null;
  if (appInstance) return appInstance;
  appInstance = getApps()[0] ?? initializeApp(firebaseConfig);
  return appInstance;
}

export function getFirebaseAuth(): Auth | null {
  if (authInstance) return authInstance;
  const app = getFirebaseApp();
  if (!app) return null;
  authInstance = getAuth(app);
  return authInstance;
}

export function subscribeToAuthState(
  callback: (user: User | null) => void,
): () => void {
  const auth = getFirebaseAuth();
  if (!auth) {
    // Not configured (e.g. build time or missing env). Report signed-out.
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(auth, callback);
}

/**
 * Which identity a request should be made as.
 *
 * The platform runs ONE auth mode at a time, so `"active"` is almost always
 * right and is the default. The other values exist for forks that run two
 * audiences concurrently. `"firebase"` is retained as the historical name
 * for the individually-identified audience; in local-jwt deployments it
 * resolves to the current built-in JWT rather than Firebase.
 */
export type AuthAudience = "active" | "firebase" | "group" | "either";

/** Resolve a token for a specific audience. */
export async function getIdTokenFor(
  audience: AuthAudience = "active",
  forceRefresh = false,
): Promise<string | null> {
  if (audience === "active") return getIdToken(forceRefresh);

  const groupToken = () => readStoredGroupSession()?.token ?? null;
  const individualToken = async () => {
    if (isOidcAuthMode()) return getOidcToken();
    if (isLocalJwtAuthMode()) return getLocalJwtToken();
    if (isLocalMode()) return LOCAL_MODE_STUB_TOKEN;
    const auth = getFirebaseAuth();
    if (!auth?.currentUser) return null;
    return auth.currentUser.getIdToken(forceRefresh);
  };

  if (audience === "group") return groupToken();
  if (audience === "firebase") return individualToken();
  return (await individualToken()) ?? groupToken();
}

export async function getIdToken(forceRefresh = false): Promise<string | null> {
  // Anonymous group-ID mode is an explicit deployment mode and takes priority.
  if (isAnonymousGroupAuthMode()) {
    const session = readStoredGroupSession();
    return session?.token ?? null;
  }
  // Self-host local JWT must be checked before LOCAL_MODE because the current
  // Compose uses LOCAL_MODE=1 to switch off GCP assumptions while still using
  // a real PostgreSQL-backed identity provider.
  if (isOidcAuthMode()) return getOidcToken();
  if (isLocalJwtAuthMode()) return getLocalJwtToken();
  // Development stub.
  if (isLocalMode()) return LOCAL_MODE_STUB_TOKEN;
  const auth = getFirebaseAuth();
  if (!auth?.currentUser) return null;
  return auth.currentUser.getIdToken(forceRefresh);
}

/**
 * Subscribe to ID-token changes.
 *
 * Firebase rotates automatically. Local JWT currently has no refresh token;
 * subscribers are notified on login/logout/session expiry so long-lived AG-UI
 * agents update their Authorization header instead of retaining a stale token.
 */
export function subscribeToIdToken(
  callback: (token: string | null) => void,
): () => void {
  if (isAnonymousGroupAuthMode()) {
    const session = readStoredGroupSession();
    callback(session?.token ?? null);
    return () => {};
  }
  if (isOidcAuthMode()) {
    return subscribeToOidcToken(callback);
  }
  if (isLocalJwtAuthMode()) {
    return subscribeToLocalJwtToken(callback);
  }
  if (isLocalMode()) {
    callback(LOCAL_MODE_STUB_TOKEN);
    return () => {};
  }
  const auth = getFirebaseAuth();
  if (!auth) {
    callback(null);
    return () => {};
  }
  return onIdTokenChanged(auth, () => {
    void getIdToken().then((t) => callback(t));
  });
}

/** Sign in with Google for Firebase deployments. */
export async function signInWithGoogle(): Promise<void> {
  const auth = getFirebaseAuth();
  if (!auth) throw new Error("firebase not configured");
  const provider = new GoogleAuthProvider();
  await signInWithPopup(auth, provider);
}

export async function signInWithGoogleRedirect(): Promise<void> {
  const auth = getFirebaseAuth();
  if (!auth) throw new Error("firebase not configured");
  const provider = new GoogleAuthProvider();
  await signInWithRedirect(auth, provider);
}

export async function signOut(): Promise<void> {
  const auth = getFirebaseAuth();
  if (!auth) return;
  await fbSignOut(auth);
}

export function getFirestoreDb(): Firestore | null {
  const app = getFirebaseApp();
  if (!app) return null;
  return getFirestore(app);
}

export function firestoreTimestampToIso(value: unknown): string | null {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null && "toDate" in value) {
    const d = (value as { toDate: () => Date }).toDate?.();
    return d instanceof Date ? d.toISOString() : null;
  }
  return null;
}

export type { User };
