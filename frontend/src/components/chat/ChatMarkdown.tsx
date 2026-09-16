"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { InlineCitation, isCitationHref } from "@/components/chat/InlineCitation";
import { CodeBlock, hastLanguage, hastText } from "@/components/chat/CodeBlock";
import { SVGBlock } from "@/components/chat/media/SVGBlock";
import { InlineImage } from "@/components/chat/media/InlineImage";
import { PDFCard } from "@/components/chat/media/PDFCard";
import type { Components } from "react-markdown";

interface ChatMarkdownProps {
  content: string;
  navigateToBlock: (docId: string, blockId: string) => void;
}

// Unique sentinel that won't appear in real markdown content.
// Pre-processing extracts ```svg blocks before react-markdown/rehypeHighlight
// sees them, because rehypeHighlight recognises 'svg' as an alias for its XML
// highlighter and transforms the text content into React span elements — making
// String(children) useless inside the code renderer. By replacing svg fences
// with this sentinel we bypass the pipeline and render SVGBlock directly.
const SVG_SENTINEL_PREFIX = "AIPSVGBLOCK";
const SVG_SENTINEL_SUFFIX = "END";
const SVG_FENCE_RE = /```svg\r?\n([\s\S]*?)```/g;

export function ChatMarkdown({ content, navigateToBlock }: ChatMarkdownProps) {
  const { processedContent, svgBlocks } = useMemo(() => {
    const blocks = new Map<number, string>();
    let idx = 0;
    const processed = content.replace(SVG_FENCE_RE, (_match, svgCode: string) => {
      blocks.set(idx, svgCode.trim());
      return `${SVG_SENTINEL_PREFIX}${idx++}${SVG_SENTINEL_SUFFIX}`;
    });
    return { processedContent: processed, svgBlocks: blocks };
  }, [content]);

  // MEMOISED, and that is load-bearing (v6.19.0, AIPLA #44).
  // react-markdown treats each entry in `components` as a React element TYPE.
  // A fresh object identity per render therefore makes React REMOUNT the whole
  // rendered subtree rather than re-render it — every message's DOM torn down
  // and rebuilt on any parent re-render.
  const components: Components = useMemo(() => ({
    a({ href, children }) {
      const h = href ?? "#";
      // Current and legacy citation-scheme links → InlineCitation chip.
      if (isCitationHref(h)) {
        return (
          <InlineCitation href={h} navigateToBlock={navigateToBlock}>
            {children}
          </InlineCitation>
        );
      }
      const safePdf =
        h.startsWith("https://") || h.startsWith("http://") ? h : null;
      if (safePdf && safePdf.toLowerCase().endsWith(".pdf")) {
        return <PDFCard url={safePdf} />;
      }
      const safe =
        h.startsWith("https://") || h.startsWith("http://") || h.startsWith("mailto:")
          ? h
          : "#";
      return (
        <a href={safe} target="_blank" rel="noopener noreferrer" className="text-teal-600 underline">
          {children}
        </a>
      );
    },
    img({ src, alt }) {
      if (!src || typeof src !== "string") return null;
      return <InlineImage src={src} alt={alt} />;
    },
    html() {
      return null;
    },
    p({ children }) {
      const first = Array.isArray(children) ? children[0] : children;
      if (typeof first === "string") {
        const match = first.match(new RegExp(`^${SVG_SENTINEL_PREFIX}(\\d+)${SVG_SENTINEL_SUFFIX}$`));
        if (match) {
          const svgString = svgBlocks.get(parseInt(match[1]));
          if (svgString) return <SVGBlock svgString={svgString} />;
        }
      }
      return <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>;
    },
    h1({ children }) {
      return <h1 className="mb-2 text-base font-semibold">{children}</h1>;
    },
    h2({ children }) {
      return <h2 className="mb-2 text-sm font-semibold">{children}</h2>;
    },
    h3({ children }) {
      return <h3 className="mb-1 text-sm font-medium">{children}</h3>;
    },
    ul({ children }) {
      return <ul className="mb-2 list-disc pl-4 space-y-0.5">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="mb-2 list-decimal pl-4 space-y-0.5">{children}</ol>;
    },
    li({ children }) {
      return <li className="text-sm">{children}</li>;
    },
    strong({ children }) {
      return <strong className="font-semibold">{children}</strong>;
    },
    em({ children }) {
      return <em className="italic">{children}</em>;
    },
    code({ className, children, ...props }) {
      const classes = className?.split(/\s+/) ?? [];
      const langClass = classes.find((c) => c.startsWith("language-"));
      const isBlock = !!langClass;

      if (isBlock) {
        return (
          <code className={`${className ?? ""} text-xs`} {...props}>
            {children}
          </code>
        );
      }
      return (
        <code className="rounded bg-muted px-1 py-0.5 text-xs font-mono" {...props}>
          {children}
        </code>
      );
    },
    pre({ children, node }) {
      return (
        <CodeBlock text={hastText(node)} language={hastLanguage(node)}>
          {children}
        </CodeBlock>
      );
    },
    table({ children }) {
      return (
        <div className="mb-2 overflow-x-auto">
          <table className="w-full text-xs border-collapse">{children}</table>
        </div>
      );
    },
    th({ children }) {
      return (
        <th className="border border-border bg-muted px-2 py-1 text-left font-medium">
          {children}
        </th>
      );
    },
    td({ children }) {
      return <td className="border border-border px-2 py-1">{children}</td>;
    },
    blockquote({ children }) {
      return (
        <blockquote className="mb-2 border-l-2 border-muted-foreground/40 pl-3 text-muted-foreground">
          {children}
        </blockquote>
      );
    },
  }), [navigateToBlock, svgBlocks]);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }]]}
      components={components}
      urlTransform={(url) => {
        // Preserve current + legacy citation URIs before react-markdown sanitizes
        // them; old persisted conversations must remain navigable after rebrand.
        if (
          isCitationHref(url) ||
          url.startsWith("https://") ||
          url.startsWith("http://") ||
          url.startsWith("mailto:")
        ) {
          return url;
        }
        return "#";
      }}
    >
      {processedContent}
    </ReactMarkdown>
  );
}
