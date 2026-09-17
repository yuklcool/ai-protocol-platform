"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { translateChat } from "@/lib/i18n/chat";

interface SkillNotFoundProps {
  /** Slug from the URL; displayed as a runtime identifier when present. */
  slug?: string;
}

interface WhoAmI {
  email?: string;
  groupTags?: string[];
}

export function SkillNotFound({ slug }: SkillNotFoundProps) {
  const { user, signOut } = useAuth();
  const { locale } = useI18n();
  const [identity, setIdentity] = useState<WhoAmI | null>(null);

  useEffect(() => {
    if (!user) return;
    fetchWithAuth("/api/proxy/api/auth/whoami")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setIdentity({ email: data.email, groupTags: data.groupTags ?? [] });
      })
      .catch(() => {
        setIdentity({ email: user.email ?? undefined, groupTags: [] });
      });
  }, [user]);

  const email = identity?.email ?? user?.email ?? translateChat(locale, "notFound.unknownAccount");
  const tags = identity?.groupTags ?? null;
  const headline = slug
    ? translateChat(locale, "notFound.withSlug", { slug })
    : translateChat(locale, "notFound.generic");

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="max-w-lg space-y-3">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          {translateChat(locale, "notFound.eyebrow")}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
          {headline}
        </h1>
        <p className="text-sm text-muted-foreground">
          {translateChat(locale, "notFound.description")}
        </p>
        <div className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-left text-xs text-muted-foreground">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider opacity-70">
              {translateChat(locale, "notFound.signedInAs")}
            </span>
            <span className="font-mono text-foreground">{email}</span>
          </div>
          {tags !== null && (
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wider opacity-70">
                {translateChat(locale, "notFound.groups")}
              </span>
              {tags.length > 0 ? (
                <span className="font-mono">{tags.join(", ")}</span>
              ) : (
                <span className="italic">{translateChat(locale, "notFound.none")}</span>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-col items-center gap-3">
        <button
          type="button"
          onClick={() => void signOut()}
          className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
        >
          {translateChat(locale, "notFound.switchAccount")}
        </button>
        <Link
          href="/"
          className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {translateChat(locale, "notFound.backHome")}
        </Link>
      </div>
    </main>
  );
}
