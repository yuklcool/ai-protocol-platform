"use client";

import { type FormEvent, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { isLocalJwtAuthMode } from "@/lib/localJwtAuth";
import { isOidcAuthMode } from "@/lib/oidcAuth";
import { cn } from "@/lib/utils";

/** Authentication control for Firebase and built-in self-host JWT modes. */
export function SignInButton() {
  const { t } = useI18n();
  const { user, loading, signIn, signInWithRedirect, signInWithPassword, signOut } = useAuth();
  const localJwt = isLocalJwtAuthMode();
  const oidc = isOidcAuthMode();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLocalLogin, setShowLocalLogin] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleInteractiveSignIn = async () => {
    setBusy(true);
    setError(null);
    if (oidc) {
      try {
        await signInWithRedirect();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setBusy(false);
      }
      return;
    }

    try {
      await signIn();
    } catch (popupErr) {
      console.warn("popup sign-in failed, falling back to redirect", popupErr);
      try {
        await signInWithRedirect();
      } catch (redirectErr) {
        setError(String(redirectErr));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleLocalSignIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!signInWithPassword) return;
    setBusy(true);
    setError(null);
    try {
      await signInWithPassword(email, password);
      setPassword("");
      setShowLocalLogin(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("auth.failed");
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const handleSignOut = async () => {
    setBusy(true);
    setError(null);
    try {
      await signOut();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <span className="text-xs text-muted-foreground" data-testid="sign-in-loading">
        {t("auth.checking")}
      </span>
    );
  }

  if (user) {
    return (
      <div className="flex items-center gap-3" data-testid="signed-in">
        <span className="max-w-48 truncate text-sm text-muted-foreground">{user.email}</span>
        <button
          type="button"
          onClick={handleSignOut}
          disabled={busy}
          className={cn(
            "rounded-md border border-input bg-background px-3 py-1.5 text-sm",
            "hover:bg-muted disabled:opacity-50",
          )}
        >
          {t("auth.signOut")}
        </button>
      </div>
    );
  }

  if (localJwt) {
    return (
      <Dialog.Root open={showLocalLogin} onOpenChange={(open) => { if (!busy) setShowLocalLogin(open); }}>
        <Dialog.Trigger asChild>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setShowLocalLogin(true);
          }}
          data-testid="sign-in-button"
          className={cn(
            "button-primary px-4 py-2 text-sm font-medium ",
            "hover:opacity-90",
          )}
        >
          {t("auth.signIn")}
        </button>

        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/30 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-[101] max-h-[90dvh] w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 overflow-y-auto glass-panel bg-popover p-6 shadow-xl">
              <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                  <Dialog.Title className="text-lg font-semibold text-foreground">
                    {t("auth.signIn")}
                  </Dialog.Title>
                  <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                    {t("auth.localDescription")}
                  </Dialog.Description>
                </div>
                <button
                  type="button"
                  aria-label={t("auth.closeSignIn")}
                  disabled={busy}
                  onClick={() => setShowLocalLogin(false)}
                  className="rounded-md px-2 py-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                >
                  ×
                </button>
              </div>

              <form className="space-y-4" onSubmit={handleLocalSignIn}>
                <label className="block space-y-1.5">
                  <span className="text-sm font-medium text-foreground">{t("auth.email")}</span>
                  <input
                    type="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                    placeholder="admin@example.com"
                  />
                </label>

                <label className="block space-y-1.5">
                  <span className="text-sm font-medium text-foreground">{t("auth.password")}</span>
                  <input
                    type="password"
                    autoComplete="current-password"
                    required
                    minLength={12}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                  />
                </label>

                {error && (
                  <div
                    className="rounded-md border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-600"
                    data-testid="sign-in-error"
                    role="alert"
                  >
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={busy || !email || password.length < 12}
                  className={cn(
                    "w-full button-primary px-4 py-2.5 text-sm font-medium ",
                    "hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50",
                  )}
                >
                  {busy ? t("auth.signingIn") : t("auth.signIn")}
                </button>
              </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={handleInteractiveSignIn}
        disabled={busy}
        data-testid="sign-in-button"
        className={cn(
          "inline-flex items-center gap-2 button-primary px-4 py-2 text-sm",
          "font-medium  hover:opacity-90 disabled:opacity-50",
        )}
      >
        {busy ? t("auth.signingIn") : oidc ? t("auth.signIn") : t("auth.signInWithGoogle")}
      </button>
      {error && (
        <span className="text-xs text-red-600" data-testid="sign-in-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
