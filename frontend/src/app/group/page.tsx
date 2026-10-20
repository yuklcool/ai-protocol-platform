"use client";

/**
 * Group-join page — sprint 2.11 M3.
 *
 * Single input + Join button. Anonymous flow:
 *   1. User pastes the short code their teacher handed out.
 *   2. We POST `/api/proxy/api/auth/group/join`; on success we redirect
 *      to `/`. On failure we render the typed error inline so the user
 *      can retry without losing their typing.
 *
 * Renders only when `NEXT_PUBLIC_AUTH_MODE=anonymous_group_id` is set.
 * Outside that mode the route still exists but tells the user this
 * deployment doesn't use anonymous-group auth (so a stray bookmark or
 * shared URL doesn't 404 — friendlier surface).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAnonymousGroupAuth } from "@/contexts/AnonymousGroupAuthProvider";
import { isAnonymousGroupAuthMode } from "@/lib/anonymousGroupAuth";

export default function GroupJoinPage() {
  if (!isAnonymousGroupAuthMode()) {
    return (
      <main className="page-container">
        <section className="page-body glass-panel flex max-w-md flex-col items-center gap-4 p-5 text-center">
          <h1 className="page-header__title">Group join not available</h1>
          <p className="notice notice--info">
            This deployment doesn&apos;t use anonymous group-ID auth. Try the
            regular sign-in flow on the home page.
          </p>
          <Link className="button-secondary min-h-11 px-4 py-2 text-sm" href="/">
            Go home
          </Link>
        </section>
      </main>
    );
  }
  return <GroupJoinForm />;
}

function GroupJoinForm() {
  const { status, error, join } = useAnonymousGroupAuth();
  const router = useRouter();
  const [code, setCode] = useState("");

  // When the provider transitions to `joined`, redirect to home. The
  // chat page's normal auth gating then sees a valid user via
  // useAuth() (wired in AuthContext.tsx).
  useEffect(() => {
    if (status === "joined") {
      router.replace("/");
    }
  }, [status, router]);

  const isJoining = status === "joining";

  async function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    try {
      await join(code);
    } catch {
      // Provider already set `error` — render below.
    }
  }

  return (
    <main className="page-container">
      <div className="page-body max-w-md space-y-6">
      <header className="page-header">
        <div className="min-w-0">
        <h1 className="page-header__title">Join your group</h1>
        <p className="page-header__desc">
          Your teacher gave you a short code (looks like{" "}
          <code className="surface-sunken px-1 py-0.5">PHYS-7K2N</code>).
          Type it below to start.
        </p>
        </div>
      </header>

      <form className="glass-panel flex flex-col gap-4 p-5" onSubmit={handleSubmit} noValidate>
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">Group code</span>
          <input
            type="text"
            autoFocus
            autoComplete="off"
            spellCheck={false}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={isJoining}
            placeholder="XXXX-XXXX"
            className="glass-control min-h-11 w-full px-3 py-2 font-mono uppercase tracking-wider"
            aria-invalid={error ? "true" : undefined}
            aria-describedby={error ? "group-error" : undefined}
          />
        </label>

        {error && <ErrorBlock error={error} />}

        <button
          type="submit"
          disabled={!code.trim() || isJoining}
          className="button-primary min-h-11 px-4 py-2 disabled:opacity-50"
        >
          {isJoining ? "Joining…" : "Join"}
        </button>
      </form>

      <footer className="text-xs text-muted-foreground">
        Anonymous sessions don&apos;t survive closing this tab. If you lose
        the code, ask your teacher for a fresh one.
      </footer>
      </div>
    </main>
  );
}

function ErrorBlock({
  error,
}: {
  error: NonNullable<ReturnType<typeof useAnonymousGroupAuth>["error"]>;
}) {
  let body: string;
  switch (error.kind) {
    case "rate_limited":
      body = `Too many tries. Try again in ${error.retryAfterSeconds}s.`;
      break;
    case "at_capacity":
      body = "This group is at capacity for today. Try again tomorrow or ask your teacher.";
      break;
    case "unknown_or_revoked":
      body = "Code not found, expired, or revoked. Ask your teacher for a fresh code.";
      break;
    case "network":
    default:
      body = `Couldn't reach the server. ${error.message}`;
  }
  return (
    <p
      id="group-error"
      role="alert"
      className="notice notice--danger"
    >
      {body}
    </p>
  );
}
