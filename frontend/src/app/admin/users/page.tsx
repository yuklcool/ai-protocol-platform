"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { LocalAccountsPanel } from "@/components/admin/LocalAccountsPanel";
import {
  action,
  consoleApi,
  control,
  errorText,
  Field,
  jsonBody,
  Notice,
  useConsoleCopy,
} from "@/components/admin/ConsolePrimitives";

type UserGroups = {
  email: string;
  uid: string;
  group_tags: string[];
  propagation?: { effective: string };
};
type Access = { tags: Array<{ tag: string; provenances: string[] }> };
export default function UsersPage() {
  const { user, loading } = useAuth();
  const t = useConsoleCopy();
  if (loading) return <main className="p-8">{t("加载中…", "Loading…")}</main>;
  if (!user) return <SignInRequired />;
  return <Users />;
}
function Users() {
  const t = useConsoleCopy();
  const scope = useAdminScope();
  const [backend, setBackend] = useState("");
  const [email, setEmail] = useState("");
  const [data, setData] = useState<UserGroups | null>(null);
  const [tag, setTag] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [access, setAccess] = useState<Access | null>(null);
  useEffect(() => {
    consoleApi<{ backend: string }>("/auth/provider")
      .then((result) => setBackend(result.backend))
      .catch((error) => setNotice(errorText(error)));
  }, []);
  const lookup = async (value: string) => {
    setEmail(value);
    setBusy(true);
    setNotice("");
    setAccess(null);
    setData(null);
    try {
      setData(
        await consoleApi<UserGroups>(
          `/admin/users/${encodeURIComponent(value.trim())}`,
        ),
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const changeTag = async (remove?: string) => {
    if (!data) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await consoleApi<UserGroups>(
        `/admin/users/${encodeURIComponent(data.email)}/groups${remove ? `/${encodeURIComponent(remove)}` : ""}`,
        remove ? { method: "DELETE" } : jsonBody("POST", { tag: tag.trim() }),
      );
      setData(result);
      setTag("");
      setAccess(null);
      setNotice(
        result.propagation?.effective === "immediate"
          ? t("权限已立即更新。", "Permissions updated immediately.")
          : t(
              "权限已保存，下次登录或令牌刷新后生效。",
              "Permissions saved. They apply after the next sign-in or token refresh.",
            ),
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="mx-auto max-w-6xl space-y-5 p-5 sm:p-8">
      <header>
        <h1 className="text-xl font-semibold">{t("用户管理", "Users")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t(
            "管理本地账号及用户分组授权。外部身份源的账号由对应身份服务维护。",
            "Manage local accounts and group grants. External-provider accounts are managed by that identity service.",
          )}
        </p>
      </header>
      <Notice>{notice}</Notice>
      {backend === "local-jwt" && scope.isPlatform && (
        <LocalAccountsPanel
          onSelect={(value) => {
            void lookup(value);
          }}
        />
      )}
      {backend === "oidc" ? (
        <Notice>
          {t(
            "当前使用 OIDC。请在身份服务中维护账号与分组，重新登录后同步。",
            "OIDC is active. Manage accounts and groups in your identity provider, then sign in again.",
          )}
        </Notice>
      ) : (
        <section className="space-y-4 rounded-lg border p-5">
          <h2 className="font-medium">
            {t("用户分组授权", "User group grants")}
          </h2>
          <form
            className="flex items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void lookup(email);
            }}
          >
            <div className="flex-1">
              <Field label={t("邮箱", "Email")}>
                <input
                  className={control}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </Field>
            </div>
            <button className={action} disabled={busy}>
              {busy ? t("查询中…", "Loading…") : t("查询用户", "Find user")}
            </button>
          </form>
          {data && (
            <div className="space-y-4">
              <p className="text-sm font-medium">{data.email}</p>
              <div className="flex flex-wrap gap-2">
                {data.group_tags.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    {t("尚未分配分组。", "No group grants.")}
                  </p>
                )}
                {data.group_tags.map((value) => (
                  <span
                    className="inline-flex items-center gap-2 rounded-md border px-2 py-1 text-sm"
                    key={value}
                  >
                    {value}
                    <button
                      aria-label={`${t("撤销", "Revoke")} ${value}`}
                      disabled={busy}
                      onClick={() => void changeTag(value)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <form
                className="flex items-end gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void changeTag();
                }}
              >
                <div className="flex-1">
                  <Field label={t("分组标签", "Group tag")}>
                    <input
                      className={control}
                      value={tag}
                      onChange={(e) => setTag(e.target.value)}
                    />
                  </Field>
                </div>
                <button className={action} disabled={busy || !tag.trim()}>
                  {t("授予分组", "Grant group")}
                </button>
              </form>
              <button
                className={action}
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    setAccess(
                      await consoleApi<Access>(
                        "/admin/access/check",
                        jsonBody("POST", { email: data.email }),
                      ),
                    );
                  } catch (error) {
                    setNotice(errorText(error));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {t("检查有效权限", "Check effective access")}
              </button>
              {access && (
                <ul className="space-y-2 text-sm">
                  {access.tags.map((row) => (
                    <li key={row.tag}>
                      {row.tag}{" "}
                      <span className="text-muted-foreground">
                        {row.provenances.join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}
    </main>
  );
}
