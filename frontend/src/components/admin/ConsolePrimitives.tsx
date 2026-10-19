"use client";

import {
  Children,
  cloneElement,
  isValidElement,
  useCallback,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";

export const control =
  "glass-control w-full px-3 py-2 text-sm disabled:opacity-50";
export const action =
  "button-secondary px-3 py-2 text-sm disabled:opacity-50";
export function useConsoleCopy() {
  const { locale } = useI18n();
  return useCallback(
    (zh: string, en: string) => (locale.startsWith("zh") ? zh : en),
    [locale],
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="block space-y-1.5">
      <label
        htmlFor={id}
        className="block text-xs font-medium text-muted-foreground"
      >
        {label}
      </label>
      {Children.map(children, (child) =>
        isValidElement(child) &&
        ["input", "select", "textarea"].includes(String(child.type))
          ? cloneElement(
              child as ReactElement<{
                id?: string;
                "aria-describedby"?: string;
              }>,
              { id, "aria-describedby": hint ? `${id}-hint` : undefined },
            )
          : child,
      )}
      {hint && (
        <span
          id={`${id}-hint`}
          className="block text-xs leading-5 text-muted-foreground"
        >
          {hint}
        </span>
      )}
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return children ? (
    <p
      role="status"
      className="glass-panel bg-muted/30 p-3 text-sm whitespace-pre-wrap"
    >
      {children}
    </p>
  ) : null;
}
export async function consoleApi<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetchWithAuth(`/api/proxy/api${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `HTTP ${response.status}`,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
export function jsonBody(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
