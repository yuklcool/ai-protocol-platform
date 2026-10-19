// Platform settings — the platform preamble editor (v6.14.0). The preamble is
// PREPENDED to every skill's agent prompt (shared identity / house-style /
// guardrails), so this is an aitana-admin-only, audited surface. A 403 renders
// the "admins only" state; loading / saving / error all render (never-silent).
//
// Mirrors the group-tags admin page: probe on load, edit + PUT, re-read on save.

"use client";
import { useConsoleCopy } from "@/components/admin/ConsolePrimitives";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { SignInRequired } from "@/components/chat/SignInRequired";
import {
  CompactionSettingsSection,
  type CompactionSettings,
} from "./CompactionSettings";

type PlatformConfig = {
  preamble: string;
  enabled: boolean;
  compaction?: CompactionSettings;
  updatedBy?: string;
  updatedAt?: number;
};

const ENDPOINT = "/api/proxy/api/admin/platform-config";
const PREAMBLE_MAX_LEN = 20000;

type Probe = "loading" | "admin" | "forbidden" | "error";

export default function PlatformSettingsPage() {
  const t = useConsoleCopy();
  const { user, loading } = useAuth();
  const [probe, setProbe] = useState<Probe>("loading");

  const [preamble, setPreamble] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [meta, setMeta] = useState<{ updatedBy?: string; updatedAt?: number }>(
    {},
  );
  const [compaction, setCompaction] = useState<CompactionSettings | null>(null);
  const [defaultPrompt, setDefaultPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    try {
      const r = await fetchWithAuth(ENDPOINT);
      if (r.status === 403) return setProbe("forbidden");
      if (!r.ok) return setProbe("error");
      const cfg: PlatformConfig = await r.json();
      setPreamble(cfg.preamble ?? "");
      setEnabled(cfg.enabled ?? true);
      setCompaction(cfg.compaction ?? {});
      setMeta({ updatedBy: cfg.updatedBy, updatedAt: cfg.updatedAt });
      setProbe("admin");

      // Shipped defaults, so the prompt editor opens on the real text. Fetched
      // separately (they are computed, never stored) and non-blocking — the
      // panel still works if this fails, just with an empty prompt box.
      try {
        const d = await fetchWithAuth(`${ENDPOINT}/defaults`);
        if (d.ok) setDefaultPrompt((await d.json()).summarizerPrompt ?? "");
      } catch {
        /* leave the box empty — "empty = shipped default" still holds */
      }
    } catch {
      setProbe("error");
    }
  };

  useEffect(() => {
    if (loading || !user) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user]);

  const save = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await fetchWithAuth(ENDPOINT, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preamble, enabled }),
      });
      if (!r.ok) {
        const detail = await r.json().catch(() => null);
        setNotice(
          detail?.detail ||
            t(
              "无法保存全局公共指令。",
              "Could not save the platform preamble.",
            ),
        );
        return;
      }
      const cfg: PlatformConfig = await r.json();
      setMeta({ updatedBy: cfg.updatedBy, updatedAt: cfg.updatedAt });
      setNotice(
        t(
          "已保存，新对话将使用更新后的公共指令。",
          "Saved. New chats will use the updated preamble within a minute.",
        ),
      );
    } catch {
      setNotice(
        t("无法保存全局公共指令。", "Could not save the platform preamble."),
      );
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Centered>{t("加载中…", "Loading…")}</Centered>;
  if (!user) return <SignInRequired />;
  if (probe === "forbidden") {
    return (
      <Centered>
        <div className="max-w-md text-center">
          <h1 className="mb-2 text-lg font-semibold">
            {t("需要管理员权限", "Admins only")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("平台设置需要", "Platform settings require the")}
            <code>aitana-admin</code>
            {t("权限组。", "group.")}
          </p>
        </div>
      </Centered>
    );
  }
  if (probe === "loading")
    return <Centered>{t("加载中…", "Loading…")}</Centered>;
  if (probe === "error")
    return (
      <Centered>
        {t(
          "无法加载平台设置，请重试。",
          "Something went wrong loading platform settings.",
        )}
      </Centered>
    );

  const overLimit = preamble.length > PREAMBLE_MAX_LEN;

  return (
    <main className="page-container mx-auto max-w-3xl p-6">
      <header className="mb-4">
        <h1 className="text-xl font-semibold">
          {t("平台设置", "Platform settings")}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t(
            "平台公共指令会加入每次对话，统一身份、表达风格和边界；Root Agent 和能力包在此基础上补充各自指令。修改约一分钟内对新对话生效。",
            "The platform preamble adds shared identity, style and guardrails to every conversation. Root and capability instructions follow it. Changes apply to new chats within about a minute.",
          )}
        </p>
      </header>

      <section className="glass-panel p-4">
        <label className="mb-2 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span>
            {t(
              "启用全局公共指令",
              "Enabled — prepend this preamble to every skill",
            )}
          </span>
        </label>

        <textarea
          className="mt-2 h-72 w-full rounded-md border px-3 py-2 font-mono text-sm"
          placeholder={t("输入平台公共指令…", "Enter the platform preamble…")}
          value={preamble}
          onChange={(e) => setPreamble(e.target.value)}
          disabled={!enabled}
        />
        <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
          <span className={overLimit ? "text-red-600" : undefined}>
            {preamble.length.toLocaleString()} /{" "}
            {PREAMBLE_MAX_LEN.toLocaleString()}
            {t("字符", "characters")}
          </span>
          {meta.updatedBy && (
            <span>
              {t("最近修改人", "Last edited by")}
              <code>{meta.updatedBy}</code>
              {meta.updatedAt
                ? ` · ${new Date(meta.updatedAt * 1000).toLocaleString()}`
                : ""}
            </span>
          )}
        </div>

        <div className="mt-3 flex items-center justify-end gap-3">
          {notice && <p className="text-xs text-muted-foreground">{notice}</p>}
          <button
            onClick={save}
            disabled={busy || overLimit}
            className="rounded-md border px-3 py-2 text-sm hover:bg-muted/40 disabled:opacity-50"
          >
            {busy ? t("保存中…", "Saving…") : "Save"}
          </button>
        </div>
      </section>

      <p className="mt-4 text-xs text-muted-foreground">
        This text is sent to every model provider on every turn, for every skill
        and tenant. Keep it generic — anything customer- or skill-specific
        belongs in that skill instead.
      </p>

      {compaction && (
        <CompactionSettingsSection
          // Remount when the shipped prompt arrives so the textarea seeds from
          // it (the section holds its own draft state).
          key={defaultPrompt ? "with-default" : "no-default"}
          initial={compaction}
          defaultPrompt={defaultPrompt}
          onSaved={(updatedBy, updatedAt) => setMeta({ updatedBy, updatedAt })}
        />
      )}
    </main>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <main className="page-container flex min-h-screen items-center justify-center p-8">
      {children}
    </main>
  );
}
