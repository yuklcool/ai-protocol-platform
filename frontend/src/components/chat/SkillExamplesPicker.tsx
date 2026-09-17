"use client";

import type { ExampleDocument, ExamplePrompt } from "@/types/skill";
import { cn } from "@/lib/utils";
import { DocumentThumbnail } from "@/components/document/DocumentThumbnail";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface SkillExamplesPickerProps {
  examples: ExampleDocument[];
  onPickExample: (example: ExampleDocument) => void;
  prompts?: ExamplePrompt[];
  onPickPrompt?: (prompt: string) => void;
  onUploadOwn?: () => void;
  layout?: "panel" | "canvas";
}

export function SkillExamplesPicker({
  examples,
  onPickExample,
  prompts = [],
  onPickPrompt,
  onUploadOwn,
  layout = "panel",
}: SkillExamplesPickerProps) {
  const { locale } = useI18n();
  const showPrompts = prompts.length > 0 && Boolean(onPickPrompt);
  if (examples.length === 0 && !showPrompts) return null;
  const isCanvas = layout === "canvas";
  return (
    <div className={cn("flex flex-col gap-6 p-6", !isCanvas && "h-full overflow-auto")}>
      {showPrompts && (
        <section className="space-y-3" data-testid="example-prompts">
          <div className="space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              {translateChat(locale, "examples.tryOne")}
            </p>
            <h3 className="text-lg font-semibold tracking-tight text-foreground">
              {translateChat(locale, "examples.capabilities")}
            </h3>
            <p className="text-sm text-muted-foreground">
              {translateChat(locale, "examples.realRun")}
            </p>
          </div>
          <ul className="grid gap-2 sm:grid-cols-2">
            {prompts.map((p, i) => (
              <li
                key={p.label}
                className="animate-in fade-in-0 slide-in-from-bottom-2 fill-mode-both"
                style={{ animationDelay: `${i * 50}ms`, animationDuration: "350ms" }}
              >
                <button
                  type="button"
                  onClick={() => onPickPrompt?.(p.prompt)}
                  title={p.prompt}
                  className="group flex h-full w-full flex-col gap-1 rounded-lg border border-border bg-background p-3 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/50 hover:bg-muted/40 hover:shadow-md focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                >
                  {p.badge && (
                    <span className="w-fit rounded-md bg-primary/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-primary">
                      {p.badge}
                    </span>
                  )}
                  <span className="text-sm font-semibold leading-tight text-foreground group-hover:text-primary">
                    {p.label}
                  </span>
                  {p.summary && (
                    <span className="line-clamp-2 text-xs leading-snug text-muted-foreground">{p.summary}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {examples.length > 0 && (
        <div className="space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {showPrompts
              ? translateChat(locale, "examples.orDocument")
              : translateChat(locale, "examples.tryExample")}
          </p>
          <h3 className="text-lg font-semibold tracking-tight text-foreground">
            {translateChat(locale, "examples.pickDocument")}
          </h3>
          <p className="text-sm text-muted-foreground">
            {translateChat(locale, "examples.documentHelp")}
          </p>
        </div>
      )}

      <ul
        className={cn(
          "grid gap-3",
          examples.length === 0 && "hidden",
          isCanvas
            ? "[grid-template-columns:repeat(auto-fill,minmax(11rem,13rem))]"
            : "grid-cols-1 sm:grid-cols-2 md:grid-cols-3",
        )}
      >
        {examples.map((example, i) => (
          <li
            key={`${example.bucket}/${example.object}`}
            className="animate-in fade-in-0 slide-in-from-bottom-2 fill-mode-both"
            style={{ animationDelay: `${i * 60}ms`, animationDuration: "400ms" }}
          >
            <button
              type="button"
              onClick={() => onPickExample(example)}
              className="group flex h-full w-full flex-col gap-3 rounded-lg border border-border bg-background p-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/50 hover:bg-muted/40 hover:shadow-md focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <ExampleThumbnail example={example} locale={locale} />
              <div className="space-y-1">
                <p className="text-sm font-semibold leading-tight text-foreground group-hover:text-primary">
                  {example.label}
                </p>
                {example.summary && (
                  <p className="line-clamp-2 text-xs leading-snug text-muted-foreground">
                    {example.summary}
                  </p>
                )}
              </div>
            </button>
          </li>
        ))}
      </ul>

      {onUploadOwn && (
        <div className="border-t border-border pt-4">
          <button
            type="button"
            onClick={onUploadOwn}
            className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground transition-colors hover:text-primary"
          >
            {translateChat(locale, "examples.uploadOwn")}
          </button>
        </div>
      )}
    </div>
  );
}

function ExampleThumbnail({
  example,
  locale,
}: {
  example: ExampleDocument;
  locale: "zh-CN" | "en";
}) {
  const alt = translateChat(locale, "examples.firstPageAlt", { label: example.label });
  return (
    <div className="relative aspect-[3/4] overflow-hidden rounded-md border border-border bg-white">
      {example.thumbnail ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={example.thumbnail} alt={alt} className="h-full w-full object-cover" />
      ) : (
        <DocumentThumbnail
          source={{ kind: "bucket", bucket: example.bucket, object: example.object }}
          alt={alt}
        />
      )}
    </div>
  );
}
