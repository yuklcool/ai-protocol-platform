"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  AnonymousGroupAuthProvider,
  useAnonymousGroupAuth,
} from "@/contexts/AnonymousGroupAuthProvider";
import { isAnonymousGroupAuthMode } from "@/lib/anonymousGroupAuth";
import {
  getIdToken as fbGetIdToken,
  signInWithGoogle as fbSignInWithGoogle,
  signInWithGoogleRedirect as fbSignInWithGoogleRedirect,
  signOut as fbSignOut,
  subscribeToAuthState,
  type User,
} from "@/lib/firebase";
import {
  clearLocalJwtSession,
  isLocalJwtAuthMode,
  LOCAL_JWT_AUTH_CHANGED_EVENT,
  loginWithLocalJwt,
  readLocalJwtSession,
  validateLocalJwtSession,
  type LocalJwtUser,
} from "@/lib/localJwtAuth";
import {
  isLocalMode,
  LOCAL_MODE_STUB_TOKEN,
  LOCAL_MODE_WORKSHOP_USER,
} from "@/lib/localMode";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  getIdToken: () => Promise<string | null>;
  signIn: () => Promise<void>;
  signInWithRedirect: () => Promise<void>;
  /** Present only for the built-in self-host local-jwt provider. */
  signInWithPassword?: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Build a Firebase-User-shaped stub for LOCAL_MODE. Consumers reading
 * `uid` / `email` / `displayName` get what they expect; methods on the
 * real SDK aren't present (which is correct — LOCAL_MODE has no SDK). */
function buildLocalModeStubUser(): User {
  return {
    uid: LOCAL_MODE_WORKSHOP_USER.uid,
    email: LOCAL_MODE_WORKSHOP_USER.email,
    displayName: LOCAL_MODE_WORKSHOP_USER.displayName,
    photoURL: LOCAL_MODE_WORKSHOP_USER.photoURL,
  } as unknown as User;
}

function buildLocalJwtUser(user: LocalJwtUser): User {
  return {
    uid: user.uid,
    email: user.email,
    displayName: user.email,
    photoURL: null,
  } as unknown as User;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Anonymous group-ID mode is an explicit deployment mode and keeps priority.
  if (isAnonymousGroupAuthMode()) {
    return (
      <AnonymousGroupAuthProvider>
        <AnonymousGroupAuthAdapter>{children}</AnonymousGroupAuthAdapter>
      </AnonymousGroupAuthProvider>
    );
  }

  // Built-in self-host identity must be checked BEFORE LOCAL_MODE. The current
  // self-host Compose still uses LOCAL_MODE=1 to disable GCP assumptions while
  // AUTH_BACKEND=local-jwt provides the real identity boundary.
  if (isLocalJwtAuthMode()) {
    return <LocalJwtAuthProvider>{children}</LocalJwtAuthProvider>;
  }

  // LOCAL_MODE development stub: no Firebase listeners or sign-in screen.
  if (isLocalMode()) {
    return (
      <AuthContext.Provider
        value={{
          user: buildLocalModeStubUser(),
          loading: false,
          getIdToken: async () => LOCAL_MODE_STUB_TOKEN,
          signIn: async () => {},
          signInWithRedirect: async () => {},
          signOut: async () => {},
        }}
      >
        {children}
      </AuthContext.Provider>
    );
  }

  return <FirebaseAuthProvider>{children}</FirebaseAuthProvider>;
}

function LocalJwtAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const hydrate = async () => {
      const stored = readLocalJwtSession();
      if (!stored) {
        if (!cancelled) {
          setUser(null);
          setLoading(false);
        }
        return;
      }
      try {
        const validated = await validateLocalJwtSession(stored);
        if (!cancelled) setUser(validated ? buildLocalJwtUser(validated.user) : null);
      } catch {
        clearLocalJwtSession();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void hydrate();

    const onAuthChanged = () => {
      const next = readLocalJwtSession();
      setUser(next ? buildLocalJwtUser(next.user) : null);
    };
    window.addEventListener(LOCAL_JWT_AUTH_CHANGED_EVENT, onAuthChanged);
    return () => {
      cancelled = true;
      window.removeEventListener(LOCAL_JWT_AUTH_CHANGED_EVENT, onAuthChanged);
    };
  }, []);

  const signInWithPassword = async (email: string, password: string) => {
    const session = await loginWithLocalJwt(email, password);
    setUser(buildLocalJwtUser(session.user));
  };

  const localSignOut = async () => {
    clearLocalJwtSession();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        getIdToken: async () => readLocalJwtSession()?.token ?? null,
        signIn: async () => {
          throw new Error("Email/password sign-in is required for this deployment");
        },
        signInWithRedirect: async () => {
          throw new Error("Redirect sign-in is unavailable for this deployment");
        },
        signInWithPassword,
        signOut: localSignOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/** Bridge AnonymousGroupAuth state to the main AuthContext shape so
 * the rest of the app (e.g. `useAuth().user`) doesn't need to branch
 * on auth mode. */
function AnonymousGroupAuthAdapter({ children }: { children: ReactNode }) {
  const group = useAnonymousGroupAuth();
  const user: User | null = group.user
    ? ({
        uid: group.user.uid,
        email: group.user.email,
        displayName: group.user.displayName,
        photoURL: group.user.photoURL,
      } as unknown as User)
    : null;
  return (
    <AuthContext.Provider
      value={{
        user,
        loading: false,
        getIdToken: async () => group.token,
        signIn: async () => {},
        signInWithRedirect: async () => {},
        signOut: async () => {
          group.clearStoredToken();
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

function FirebaseAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = subscribeToAuthState((nextUser) => {
      setUser(nextUser);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        getIdToken: fbGetIdToken,
        signIn: fbSignInWithGoogle,
        signInWithRedirect: fbSignInWithGoogleRedirect,
        signOut: fbSignOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
