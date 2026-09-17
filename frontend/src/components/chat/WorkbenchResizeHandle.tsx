"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { RATIO_MAX, RATIO_MIN } from "@/hooks/useResizableWorkspaceRatio";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

const SNAP_POINTS: ReadonlyArray<number> = [0.3, 0.5, 0.7, 1.0];
const SNAP_RANGE = 0.025;
const SNAP_EPSILON = 1e-9;
const KEYBOARD_STEP = 0.05;

interface WorkbenchResizeHandleProps {
  ratio: number;
  onChange: (next: number) => void;
  rowSelector?: string;
}

export function WorkbenchResizeHandle({
  ratio,
  onChange,
  rowSelector = "[data-workspace-row]",
}: WorkbenchResizeHandleProps) {
  const { locale } = useI18n();
  const dividerRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [flashKey, setFlashKey] = useState(0);
  const lastSnappedRef = useRef<number | null>(null);

  const computeRatio = useCallback(
    (clientX: number): number => {
      const el = dividerRef.current;
      if (!el) return ratio;
      const row = el.closest<HTMLElement>(rowSelector) ?? document.documentElement;
      const rect = row.getBoundingClientRect();
      if (rect.width <= 0) return ratio;
      const raw = (rect.right - clientX) / rect.width;
      return Math.min(RATIO_MAX, Math.max(RATIO_MIN, raw));
    },
    [ratio, rowSelector],
  );

  const applyRatio = useCallback(
    (raw: number) => {
      const rounded = Math.round(raw * 10000) / 10000;
      let next = rounded;
      let snappedTo: number | null = null;
      for (const sp of SNAP_POINTS) {
        if (Math.abs(rounded - sp) <= SNAP_RANGE + SNAP_EPSILON) {
          next = sp;
          snappedTo = sp;
          break;
        }
      }
      if (snappedTo !== null && snappedTo !== lastSnappedRef.current) {
        setFlashKey((k) => k + 1);
        lastSnappedRef.current = snappedTo;
      } else if (snappedTo === null) {
        lastSnappedRef.current = null;
      }
      onChange(next);
    },
    [onChange],
  );

  useEffect(() => {
    if (!dragging) return;
    function onMove(e: PointerEvent) {
      applyRatio(computeRatio(e.clientX));
    }
    function onUp() {
      setDragging(false);
    }
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [dragging, applyRatio, computeRatio]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      let next: number | null = null;
      switch (e.key) {
        case "ArrowLeft":
          next = ratio - KEYBOARD_STEP;
          break;
        case "ArrowRight":
          next = ratio + KEYBOARD_STEP;
          break;
        case "Home":
          next = RATIO_MIN;
          break;
        case "End":
          next = RATIO_MAX;
          break;
        case "Enter":
          next = 0.5;
          break;
        default:
          return;
      }
      e.preventDefault();
      const clamped = Math.min(RATIO_MAX, Math.max(RATIO_MIN, next ?? ratio));
      applyRatio(clamped);
    },
    [ratio, applyRatio],
  );

  return (
    <div
      ref={dividerRef}
      role="separator"
      aria-orientation="vertical"
      aria-label={translateChat(locale, "workbench.resizeAria")}
      aria-valuenow={Math.round(ratio * 100)}
      aria-valuemin={Math.round(RATIO_MIN * 100)}
      aria-valuemax={Math.round(RATIO_MAX * 100)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      data-testid="workbench-resize-handle"
      className="group relative z-10 flex h-full w-2 shrink-0 cursor-col-resize select-none items-center justify-center focus-visible:outline-none"
    >
      <div
        key={flashKey}
        data-flash={flashKey > 0 ? "1" : undefined}
        className={[
          "pointer-events-none h-full w-px rounded-full bg-border transition-colors",
          "group-hover:bg-primary/50 group-hover:w-1 group-focus-visible:bg-primary/70 group-focus-visible:w-1",
          dragging ? "bg-primary/70 w-1" : "",
          "motion-safe:data-[flash]:animate-pulse",
        ]
          .filter(Boolean)
          .join(" ")}
      />
    </div>
  );
}
