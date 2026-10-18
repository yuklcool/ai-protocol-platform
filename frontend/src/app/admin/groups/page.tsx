// Group tags — the registry admin (v6.9.0 / 9.3). Makes a group tag first-class:
// label / description / what-it-grants. The registry is the vocabulary that
// per-user grant validation checks against (an unknown tag → 422). Also answers
// "who holds tag X" (reverse lookup). Aitana-admin gated by the backend; a 403
// renders the "admins only" state. Never-silent: loading / error / empty render.

"use client";
import { useConsoleCopy } from "@/components/admin/ConsolePrimitives";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { SignInRequired } from "@/components/chat/SignInRequired";

type GroupTag = {
  id: string;
  label?: string;
  description?: string;
  grants?: string[];
  tenant_scope?: string | null;
};
type TagMember = { email: string; uid: string };
type TagMembers = {
  tag: string;
  members: TagMember[];
  scanned: number;
  truncated: boolean;
  note: string;
};

const REGISTRY = "/api/proxy/api/admin/group-tags";
const MEMBERS = "/api/proxy/api/admin/groups";

type Probe = "loading" | "admin" | "forbidden" | "error";

export default function GroupsPage() {
  const t = useConsoleCopy();
  const { user, loading } = useAuth();
  const [probe, setProbe] = useState<Probe>("loading");
  const [tags, setTags] = useState<GroupTag[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  // Upsert form
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [grants, setGrants] = useState("");
  const [busy, setBusy] = useState(false);

  // Members lookup
  const [membersOf, setMembersOf] = useState<TagMembers | null>(null);
  const [membersBusy, setMembersBusy] = useState(false);

  const load = async () => {
    try {
      const r = await fetchWithAuth(REGISTRY);
      if (r.status === 403) return setProbe("forbidden");
      if (!r.ok) return setProbe("error");
      setTags(await r.json());
      setProbe("admin");
    } catch {
      setProbe("error");
    }
  };

  useEffect(() => {
    if (loading || !user) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user]);

  const upsert = async () => {
    const tagId = id.trim();
    if (!tagId) return;
    setBusy(true);
    setNotice(null);
    try {
      const r = await fetchWithAuth(
        `${REGISTRY}/${encodeURIComponent(tagId)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            label: label.trim(),
            description: description.trim(),
            grants: grants
              .split(",")
              .map((g) => g.trim())
              .filter(Boolean),
          }),
        },
      );
      if (!r.ok) {
        const detail = await r.json().catch(() => null);
        setNotice(detail?.detail || `Could not save "${tagId}".`);
        return;
      }
      setNotice(`Saved "${tagId}".`);
      setId("");
      setLabel("");
      setDescription("");
      setGrants("");
      await load();
    } catch {
      setNotice(`Could not save "${tagId}".`);
    } finally {
      setBusy(false);
    }
  };

  const lookupMembers = async (tag: string) => {
    setMembersBusy(true);
    setMembersOf(null);
    setNotice(null);
    try {
      const r = await fetchWithAuth(
        `${MEMBERS}/${encodeURIComponent(tag)}/members`,
      );
      if (!r.ok) {
        setNotice(`Could not look up holders of "${tag}".`);
        return;
      }
      setMembersOf(await r.json());
    } catch {
      setNotice(`Could not look up holders of "${tag}".`);
    } finally {
      setMembersBusy(false);
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
            {t("分组管理需要", "Group-tag administration requires the")}
            <code>aitana-admin</code>
            {t("权限组。", "group.")}
          </p>
        </div>
      </Centered>
    );
  }
  if (probe === "error")
    return (
      <Centered>
        {t(
          "无法加载分组，请重试。",
          "Something went wrong loading the registry.",
        )}
      </Centered>
    );

  return (
    <main className="mx-auto max-w-3xl p-6">
      <header className="mb-4">
        <h1 className="text-xl font-semibold">{t("分组标签", "Group tags")}</h1>
        <p className="text-sm text-muted-foreground">
          {t(
            "管理分组、授权能力及成员。用户授权请进入",
            "The tag registry — what each tag grants, and who holds it. Per-user grants are set under",
          )}{" "}
          <a className="underline" href="/admin/users">
            {t("用户管理", "Users")}
          </a>
          {t(
            "；未知分组无法授予。",
            "; a grant of an unregistered tag is rejected.",
          )}
        </p>
      </header>

      {/* Registry table */}
      <section className="mb-6 rounded-lg border">
        {tags.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            {t(
              "暂无分组，可在下方创建。",
              "No tags registered yet. Add the first one below.",
            )}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="px-4 py-2">{t("标签", "Tag")}</th>
                <th className="px-4 py-2">{t("授权能力", "Grants")}</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {tags.map((tag) => (
                <tr key={tag.id} className="border-b last:border-0">
                  <td className="px-4 py-2 align-top">
                    <div className="font-mono text-xs">{tag.id}</div>
                    {tag.label && (
                      <div className="text-xs text-muted-foreground">
                        {tag.label}
                      </div>
                    )}
                    {tag.description && (
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {tag.description}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 align-top text-xs text-muted-foreground">
                    {tag.grants?.length ? (
                      tag.grants.join(", ")
                    ) : (
                      <span className="opacity-50">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2 align-top text-right">
                    <button
                      onClick={() => lookupMembers(tag.id)}
                      disabled={membersBusy}
                      className="rounded-md border px-2 py-1 text-xs hover:bg-muted/40 disabled:opacity-50"
                    >
                      {t("成员", "Holders")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Members panel */}
      {membersBusy && <Note>{t("正在查询成员…", "Scanning holders…")}</Note>}
      {membersOf && (
        <section className="mb-6 rounded-lg border p-4">
          <h2 className="mb-2 text-sm font-medium">
            {t("分组成员：", "Holders of")}
            <code className="font-mono">{membersOf.tag}</code>
          </h2>
          {membersOf.members.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("暂无直接授权成员。", "No direct holders.")}
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {membersOf.members.map((m) => (
                <li
                  key={m.uid}
                  className="rounded-full border px-2 py-0.5 text-xs"
                >
                  {m.email}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            {membersOf.note}
            {membersOf.truncated &&
              " — list truncated; refine or raise the scan cap."}
          </p>
        </section>
      )}

      {/* Upsert form */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium">
          {t("新增或更新分组", "Add / update a tag")}
        </h2>
        <div className="grid gap-2">
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder={t(
              "标签标识（例如 analyst）",
              "tag id (e.g. ONE, beta-tester)",
            )}
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder={t("显示名称", "label (human name)")}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder={t(
              "说明：该分组授予哪些能力",
              "description — what holding this tag grants",
            )}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder={t(
              "授权能力标识（逗号分隔）",
              "grants (comma-separated skill slugs / capabilities)",
            )}
            value={grants}
            onChange={(e) => setGrants(e.target.value)}
          />
          <div className="flex justify-end">
            <button
              onClick={upsert}
              disabled={busy || !id.trim()}
              className="rounded-md border px-3 py-2 text-sm hover:bg-muted/40 disabled:opacity-50"
            >
              {busy ? t("保存中…", "Saving…") : "Save tag"}
            </button>
          </div>
        </div>
        {notice && (
          <p className="mt-2 text-xs text-muted-foreground">{notice}</p>
        )}
      </section>
    </main>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-6 rounded-lg border px-3 py-6 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      {children}
    </main>
  );
}
