"use client";

import { useCallback, useEffect, useState } from "react";
import { UploadDropZone } from "@/components/doc-browser/UploadDropZone";
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

type Source = {
  id: string;
  label: string;
  documentId: string;
  status: string;
  canManage: boolean;
  accessControl: { type: string };
};
type Document = { id: string; label: string; status: string };
type Search = {
  results: Array<{ source: string; excerpt: string }>;
  unavailableSources?: number;
};

export function KnowledgePanel({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (value: string[]) => void;
}) {
  const t = useConsoleCopy();
  const [sources, setSources] = useState<Source[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [sharing, setSharing] = useState("private");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Search | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try {
      const [nextSources, nextDocuments] = await Promise.all([
        consoleApi<Source[]>("/agent/knowledge/sources"),
        consoleApi<Document[]>("/agent/knowledge/documents"),
      ]);
      setSources(nextSources);
      setDocuments(nextDocuments);
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!documents.some((doc) => !["parsed", "failed"].includes(doc.status)))
      return;
    const timer = window.setInterval(() => {
      void load();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [documents, load]);
  const create = async () => {
    setBusy(true);
    setNotice("");
    try {
      const source = await consoleApi<Source>(
        "/agent/knowledge/sources",
        jsonBody("POST", { document_id: documentId, sharing }),
      );
      onChange([...new Set([...selected, source.id])]);
      await load();
      setNotice(
        t(
          "来源已创建并选中，请保存 Root Agent 设置。",
          "Source created and selected. Save Root Agent settings to apply.",
        ),
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const search = async () => {
    setBusy(true);
    setNotice("");
    setResult(null);
    try {
      setResult(
        await consoleApi<Search>(
          "/agent/knowledge/search",
          jsonBody("POST", { query }),
        ),
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        {t(
          "上传资料，选择可检索来源。来源按租户隔离，绑定后仍执行访问权限检查。",
          "Upload documents and bind searchable sources. Tenant isolation and source permissions apply on every search.",
        )}
      </p>
      <Notice>{notice}</Notice>
      <button
        type="button"
        className={action}
        disabled={busy || loading}
        onClick={() => void load()}
      >
        {t("刷新来源与解析状态", "Refresh sources and parsing status")}
      </button>
      <UploadDropZone
        skillId="root-agent"
        onUploadComplete={() => {
          void load();
        }}
      />
      <section className="space-y-3 glass-panel p-4">
        <h3 className="text-sm font-semibold">
          {t("添加知识来源", "Add a knowledge source")}
        </h3>
        <Field label={t("已上传资料", "Uploaded document")}>
          <select
            className={control}
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
          >
            <option value="">
              {t("选择已解析资料", "Select a parsed document")}
            </option>
            {documents.map((doc) => (
              <option
                key={doc.id}
                value={doc.id}
                disabled={doc.status !== "parsed"}
              >
                {doc.label} · {doc.status}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("使用范围", "Sharing")}>
          <select
            className={control}
            value={sharing}
            onChange={(e) => setSharing(e.target.value)}
          >
            <option value="private">{t("仅我可用", "Only me")}</option>
            <option value="tenant">
              {t("同租户成员可检索", "Searchable by this tenant")}
            </option>
          </select>
        </Field>
        <button
          type="button"
          className={action}
          disabled={busy || !documentId}
          onClick={() => void create()}
        >
          {busy ? t("处理中…", "Working…") : t("添加并选中", "Add and select")}
        </button>
      </section>
      <section className="space-y-3 glass-panel p-4">
        <h3 className="text-sm font-semibold">
          {t("生效来源", "Bound sources")}
        </h3>
        {loading ? (
          <p>{t("加载中…", "Loading…")}</p>
        ) : sources.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("暂无可用来源。", "No sources available.")}
          </p>
        ) : (
          sources.map((source) => (
            <div
              key={source.id}
              className="flex items-start gap-3 rounded-md border p-3"
            >
              <label className="flex min-w-0 flex-1 items-start gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(source.id)}
                  onChange={(e) =>
                    onChange(
                      e.target.checked
                        ? [...selected, source.id]
                        : selected.filter((id) => id !== source.id),
                    )
                  }
                />
                <span className="min-w-0 text-sm">
                  <span className="block break-words">{source.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {source.status} ·{" "}
                    {source.accessControl.type === "private"
                      ? t("仅我", "Private")
                      : t("同租户", "Tenant")}
                  </span>
                </span>
              </label>
              {source.canManage && (
                <>
                  <select
                    aria-label={t("来源使用范围", "Source sharing")}
                    className="max-w-32 rounded-md border bg-background p-1 text-xs"
                    value={
                      source.accessControl.type === "private"
                        ? "private"
                        : "tenant"
                    }
                    disabled={busy}
                    onChange={async (event) => {
                      setBusy(true);
                      try {
                        await consoleApi(
                          `/agent/knowledge/sources/${encodeURIComponent(source.id)}`,
                          jsonBody("PATCH", { sharing: event.target.value }),
                        );
                        await load();
                        setNotice(
                          t("来源使用范围已更新。", "Source sharing updated."),
                        );
                      } catch (error) {
                        setNotice(errorText(error));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <option value="private">{t("仅我", "Private")}</option>
                    <option value="tenant">{t("同租户", "Tenant")}</option>
                  </select>
                  <button
                    type="button"
                    className="text-xs text-destructive"
                    disabled={busy}
                    onClick={async () => {
                      if (
                        !window.confirm(
                          t(
                            "删除此知识来源？原文件会保留。",
                            "Delete this source? The original file is retained.",
                          ),
                        )
                      )
                        return;
                      setBusy(true);
                      try {
                        await consoleApi(
                          `/agent/knowledge/sources/${encodeURIComponent(source.id)}`,
                          { method: "DELETE" },
                        );
                        onChange(selected.filter((id) => id !== source.id));
                        await load();
                      } catch (error) {
                        setNotice(errorText(error));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {t("删除来源", "Delete source")}
                  </button>
                </>
              )}
            </div>
          ))
        )}
        {selected.filter((id) => !sources.some((source) => source.id === id))
          .length > 0 && (
          <p role="alert" className="text-sm text-destructive">
            {t(
              "部分已绑定来源不存在或当前无权访问，请取消这些绑定。",
              "Some bound sources are missing or inaccessible. Remove their bindings.",
            )}{" "}
            <button
              type="button"
              className="underline"
              onClick={() =>
                onChange(
                  selected.filter((id) =>
                    sources.some((source) => source.id === id),
                  ),
                )
              }
            >
              {t("清理无效绑定", "Remove unavailable bindings")}
            </button>
          </p>
        )}
      </section>
      <section className="space-y-3 glass-panel p-4">
        <h3 className="text-sm font-semibold">
          {t("验证已保存的检索配置", "Test saved retrieval settings")}
        </h3>
        <Field label={t("检索问题", "Search query")}>
          <input
            className={control}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </Field>
        <button
          type="button"
          className={action}
          disabled={busy || !query.trim()}
          onClick={() => void search()}
        >
          {t("检索", "Search")}
        </button>
        {result && (
          <div className="space-y-3">
            {result.results.length === 0 && (
              <p className="text-sm">
                {t(
                  "没有匹配内容。请确认配置已保存、来源可访问并已解析。",
                  "No matches. Check that bindings are saved and sources are parsed and accessible.",
                )}
              </p>
            )}
            {result.results.map((row, index) => (
              <blockquote
                key={index}
                className="border-l-2 border-primary pl-3 text-sm"
              >
                <p className="font-medium">{row.source}</p>
                <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
                  {row.excerpt}
                </p>
              </blockquote>
            ))}
            {!!result.unavailableSources && (
              <p className="text-sm text-destructive">
                {t("部分来源当前不可用。", "Some sources are unavailable.")}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
