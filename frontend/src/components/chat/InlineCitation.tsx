"use client";

// Citation URI scheme links (e.g. aip://doc/{docId}/block/{blockId}) are
// embedded by the agent backend. New deployments use CITATION_SCHEME, while
// older persisted conversations may still contain the historical aitana://
// form. Both must remain readable so a display-brand migration never breaks
// existing citations.

import React from "react";
import { CITATION_SCHEME } from "@/lib/branding";

const LEGACY_CITATION_SCHEMES = ["aitana"] as const;
const citationSchemes = Array.from(
  new Set([CITATION_SCHEME, ...LEGACY_CITATION_SCHEMES]),
);
const escapedSchemes = citationSchemes
  .map((scheme) => scheme.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
  .join("|");

const CITATION_URI_RE = new RegExp(
  `^(?:${escapedSchemes}):\\/\\/doc\\/([^/]+)\\/block\\/([^/]+)$`,
);
const GCS_PREFIX = "https://storage.googleapis.com";

export function isCitationHref(href: string): boolean {
  return CITATION_URI_RE.test(href);
}

interface InlineCitationProps {
  href: string;
  children: React.ReactNode;
  navigateToBlock: (docId: string, blockId: string) => void;
}

export function InlineCitation({ href, children, navigateToBlock }: InlineCitationProps) {
  const match = href.match(CITATION_URI_RE);

  if (!match) {
    const safeHref = href.startsWith(GCS_PREFIX) ? href : "#";
    return (
      <a href={safeHref} target="_blank" rel="noopener noreferrer" className="text-teal-600 underline">
        {children}
      </a>
    );
  }

  const [, docId, blockId] = match;

  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    navigateToBlock(docId, blockId);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="inline-flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-700 hover:bg-teal-100 transition-colors"
    >
      <svg
        className="h-3 w-3 shrink-0"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path d="M4 8h8M8 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {children}
    </button>
  );
}

const INLINE_LINK_RE = new RegExp(
  `\\[([^\\]]+)\\]\\(((?:${escapedSchemes}):\\/\\/[^)]+)\\)`,
  "g",
);

export function renderWithCitations(
  text: string,
  navigateToBlock: (docId: string, blockId: string) => void,
): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  INLINE_LINK_RE.lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = INLINE_LINK_RE.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }
    const [, label, href] = match;
    nodes.push(
      <InlineCitation key={match.index} href={href} navigateToBlock={navigateToBlock}>
        {label}
      </InlineCitation>,
    );
    cursor = match.index + match[0].length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes.length > 0 ? nodes : [text];
}
