from pathlib import Path
import re


def patch_file(path_str: str, replacements, regex_replacements=()):
    path = Path(path_str)
    text = path.read_text(encoding="utf-8")
    for label, old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{path}:{label}: expected exactly 1 match, found {count}")
        text = text.replace(old, new, 1)
    for label, pattern, replacement in regex_replacements:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"{path}:{label}: expected exactly 1 regex match, found {count}")
    path.write_text(text, encoding="utf-8")
    print(f"patched {path}")


# Locale pack: add final presentation keys required by the remaining Chat chrome.
patch_file(
    "frontend/src/lib/i18n/chat.ts",
    [
        (
            "en workbench resize",
            '  "workbench.closeAria": "Close {label}",\n',
            '  "workbench.closeAria": "Close {label}",\n  "workbench.resizeAria": "Resize workbench",\n',
        ),
        (
            "zh workbench resize",
            '  "workbench.closeAria": "关闭 {label}",\n',
            '  "workbench.closeAria": "关闭 {label}",\n  "workbench.resizeAria": "调整工作台宽度",\n',
        ),
        (
            "en code keys",
            '  "readAloud.stop": "Stop reading aloud",\n  "readAloud.read": "Read aloud",\n\n  "message.submitted": "Submitted",\n',
            '  "readAloud.stop": "Stop reading aloud",\n  "readAloud.read": "Read aloud",\n\n'
            '  "code.copyFailedTitle": "Copying failed — select and copy manually",\n'
            '  "code.copyTitle": "Copy to clipboard",\n'
            '  "code.copyAria": "Copy code to clipboard",\n'
            '  "code.copied": "Copied",\n'
            '  "code.copyFailed": "Copy failed",\n'
            '  "code.copy": "Copy",\n'
            '  "code.fallbackLanguage": "code",\n\n'
            '  "message.submitted": "Submitted",\n',
        ),
        (
            "zh code keys",
            '  "readAloud.stop": "停止朗读",\n  "readAloud.read": "朗读",\n\n  "message.submitted": "已提交",\n',
            '  "readAloud.stop": "停止朗读",\n  "readAloud.read": "朗读",\n\n'
            '  "code.copyFailedTitle": "复制失败，请手动选择并复制",\n'
            '  "code.copyTitle": "复制到剪贴板",\n'
            '  "code.copyAria": "复制代码到剪贴板",\n'
            '  "code.copied": "已复制",\n'
            '  "code.copyFailed": "复制失败",\n'
            '  "code.copy": "复制",\n'
            '  "code.fallbackLanguage": "代码",\n\n'
            '  "message.submitted": "已提交",\n',
        ),
        (
            "en message keys",
            '  "message.transcriptUnavailable": "This conversation is listed, but its saved messages are no longer available.",\n',
            '  "message.transcriptUnavailableTitle": "This conversation’s messages are no longer available.",\n'
            '  "message.transcriptUnavailable": "The conversation is still listed, but its transcript was removed from the session store and can’t be recovered. You can keep chatting here — new messages will be saved.",\n'
            '  "message.earlier": "Earlier in this conversation",\n'
            '  "message.startConversation": "Send a message to start the conversation.",\n',
        ),
        (
            "zh message keys",
            '  "message.transcriptUnavailable": "该对话仍在列表中，但已保存的消息内容已不可用。",\n',
            '  "message.transcriptUnavailableTitle": "此对话的历史消息已不可用。",\n'
            '  "message.transcriptUnavailable": "该对话仍保留在列表中，但历史消息已从会话存储中移除且无法恢复。你可以继续在这里对话，新消息会正常保存。",\n'
            '  "message.earlier": "本次对话的较早消息",\n'
            '  "message.startConversation": "发送一条消息开始对话。",\n',
        ),
    ],
)

# Activity panel: localize frontend chrome while preserving server-authored stages,
# errors, tool names, document names and model ids.
patch_file(
    "frontend/src/components/chat/ActivityPanel.tsx",
    [
        (
            "activity imports",
            'import { absoluteTime, formatRelative, useNow } from "@/components/activity/format";\n',
            'import { absoluteTime, useNow } from "@/components/activity/format";\n'
            'import { useI18n } from "@/contexts/I18nContext";\n'
            'import type { Locale } from "@/lib/i18n";\n'
            'import { translateChat } from "@/lib/i18n/chat";\n',
        ),
        (
            "relative helper anchor",
            '/** Pinned header showing the model + read-aloud config the session runs with. */\n',
            'function formatActivityRelative(ts: number, now: number, locale: Locale): string {\n'
            '  if (!ts) return "";\n'
            '  const diff = Math.max(0, now - ts);\n'
            '  const seconds = Math.floor(diff / 1000);\n'
            '  if (seconds < 5) return translateChat(locale, "time.justNow");\n'
            '  if (seconds < 60) return translateChat(locale, "time.secondsAgo", { count: seconds });\n'
            '  const minutes = Math.floor(seconds / 60);\n'
            '  if (minutes < 60) return translateChat(locale, "time.minutesAgo", { count: minutes });\n'
            '  const hours = Math.floor(minutes / 60);\n'
            '  if (hours < 24) return translateChat(locale, "time.hoursAgo", { count: hours });\n'
            '  return new Date(ts).toLocaleDateString(locale === "zh-CN" ? "zh-CN" : "en");\n'
            '}\n\n'
            '/** Pinned header showing the model + read-aloud config the session runs with. */\n',
        ),
        (
            "context locale",
            'function ContextRow({ context }: { context: ActivityContext }) {\n  const modelLabel = useModelLabel(context.modelTier);\n',
            'function ContextRow({ context }: { context: ActivityContext }) {\n  const { locale } = useI18n();\n  const modelLabel = useModelLabel(context.modelTier);\n',
        ),
        ("model label", '<span className="text-muted-foreground/60">Model </span>', '<span className="text-muted-foreground/60">{translateChat(locale, "activity.model")} </span>'),
        ("read aloud label", '<span className="text-muted-foreground/60">Read-aloud </span>', '<span className="text-muted-foreground/60">{translateChat(locale, "activity.readAloud")} </span>'),
        ("voice status", '<span className="font-medium text-foreground/80">{voice.enabled ? "on" : "off"}</span>', '<span className="font-medium text-foreground/80">{translateChat(locale, voice.enabled ? "activity.on" : "activity.off")}</span>'),
        (
            "tool row locale",
            'function ToolRow({ entry, now }: { entry: Extract<Entry, { kind: "tool" }>; now: number }) {\n  const [open, setOpen] = useState(false);\n',
            'function ToolRow({ entry, now }: { entry: Extract<Entry, { kind: "tool" }>; now: number }) {\n  const { locale } = useI18n();\n  const [open, setOpen] = useState(false);\n',
        ),
        ("tool relative time", '{formatRelative(entry.ts, now)}', '{formatActivityRelative(entry.ts, now, locale)}'),
        (
            "simple row locale",
            'function SimpleRow({ icon, children, ts, now }: { icon: ReactNode; children: ReactNode; ts: number; now: number }) {\n  return (\n',
            'function SimpleRow({ icon, children, ts, now }: { icon: ReactNode; children: ReactNode; ts: number; now: number }) {\n  const { locale } = useI18n();\n  return (\n',
        ),
        ("simple relative time", '{formatRelative(ts, now)}', '{formatActivityRelative(ts, now, locale)}'),
        (
            "panel locale",
            '}: ActivityPanelProps) {\n  const now = useNow();\n',
            '}: ActivityPanelProps) {\n  const { locale } = useI18n();\n  const now = useNow();\n',
        ),
        (
            "empty invitation",
            '          The assistant&apos;s activity — tools it calls, specialists it hands off to, and its reasoning —\n          shows up here as it works, then quietly stays available.\n',
            '          {translateChat(locale, "activity.empty")}\n',
        ),
        (
            "empty body",
            '            No activity yet — tools, hand-offs and documents show up here as the assistant works.\n',
            '            {translateChat(locale, "activity.none")}\n',
        ),
        ("running fallback", '{runStageLabel || "Running…"}', '{runStageLabel || translateChat(locale, "activity.running")}'),
        ("reasoning", '<span>Reasoning…</span>', '<span>{translateChat(locale, "activity.reasoning")}</span>'),
        (
            "internal toggle",
            '                    {showInternal ? "Hide" : "Show"} {internalToolCount} internal step\n                    {internalToolCount === 1 ? "" : "s"}\n',
            '                    {translateChat(\n'
            '                      locale,\n'
            '                      showInternal\n'
            '                        ? internalToolCount === 1\n'
            '                          ? "activity.hideInternalOne"\n'
            '                          : "activity.hideInternalMany"\n'
            '                        : internalToolCount === 1\n'
            '                          ? "activity.showInternalOne"\n'
            '                          : "activity.showInternalMany",\n'
            '                      { count: internalToolCount },\n'
            '                    )}\n',
        ),
        (
            "delegation prefix",
            '                    {e.mode === "suggest" ? "Suggested " : "Delegated to "}\n',
            '                    {translateChat(locale, e.mode === "suggest" ? "activity.suggested" : "activity.delegatedTo")}{" "}\n',
        ),
        (
            "document added",
            '                    Added <span className="font-medium text-foreground/80">{e.name}</span>\n',
            '                    {translateChat(locale, "activity.added")} <span className="font-medium text-foreground/80">{e.name}</span>\n',
        ),
        (
            "compaction",
            '                    <span className="font-medium text-foreground/80">History summarised</span>\n                    {" — "}\n                    {e.eventsCompacted} earlier {e.eventsCompacted === 1 ? "entry" : "entries"} condensed to keep\n                    the conversation within its context limit\n',
            '                    <span className="font-medium text-foreground/80">{translateChat(locale, "activity.historySummarised")}</span>\n'
            '                    {" — "}\n'
            '                    {translateChat(\n'
            '                      locale,\n'
            '                      e.eventsCompacted === 1 ? "activity.compactionOne" : "activity.compactionMany",\n'
            '                      { count: e.eventsCompacted },\n'
            '                    )}\n',
        ),
        ("session start", '                  Session started\n', '                  {translateChat(locale, "activity.sessionStarted")}\n'),
    ],
)

# Read-aloud button labels.
patch_file(
    "frontend/src/components/chat/ReadAloudButton.tsx",
    [
        (
            "read aloud imports",
            'import { fetchWithAuth } from "@/lib/apiClient";\n',
            'import { fetchWithAuth } from "@/lib/apiClient";\nimport { useI18n } from "@/contexts/I18nContext";\nimport { translateChat } from "@/lib/i18n/chat";\n',
        ),
        (
            "read aloud locale",
            '}: ReadAloudButtonProps) {\n  const useGCP = provider !== "browser";\n',
            '}: ReadAloudButtonProps) {\n  const { locale } = useI18n();\n  const useGCP = provider !== "browser";\n',
        ),
        (
            "read aloud label",
            '  const label = isSpeaking ? "Stop reading aloud" : "Read aloud";\n',
            '  const label = isSpeaking\n    ? translateChat(locale, "readAloud.stop")\n    : translateChat(locale, "readAloud.read");\n',
        ),
    ],
)

# Message bubble submitted label and locale-aware timestamp formatting.
patch_file(
    "frontend/src/components/chat/MessageBubble.tsx",
    [
        (
            "message imports",
            'import type { SkillMessage, ToolCallState } from "@/hooks/useSkillAgent";\n',
            'import type { SkillMessage, ToolCallState } from "@/hooks/useSkillAgent";\nimport { useI18n } from "@/contexts/I18nContext";\nimport type { Locale } from "@/lib/i18n";\nimport { translateChat } from "@/lib/i18n/chat";\n',
        ),
        (
            "format time",
            'function formatTime(timestamp?: number): string {\n  const when = typeof timestamp === "number" && Number.isFinite(timestamp) ? new Date(timestamp) : new Date();\n  return new Intl.DateTimeFormat("en", {\n',
            'function formatTime(timestamp: number | undefined, locale: Locale): string {\n  const when = typeof timestamp === "number" && Number.isFinite(timestamp) ? new Date(timestamp) : new Date();\n  return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : "en", {\n',
        ),
        (
            "message locale",
            '}: MessageBubbleProps) {\n  const isBot = message.role === "assistant";\n  const time = formatTime(timestamp);\n',
            '}: MessageBubbleProps) {\n  const { locale } = useI18n();\n  const isBot = message.role === "assistant";\n  const time = formatTime(timestamp, locale);\n',
        ),
        ("submitted", '                Submitted\n', '                {translateChat(locale, "message.submitted")}\n'),
    ],
)

# Transcript notices and empty-state text.
patch_file(
    "frontend/src/components/chat/ChatMessageList.tsx",
    [
        (
            "list imports",
            'import type React from "react";\n',
            'import type React from "react";\nimport { useI18n } from "@/contexts/I18nContext";\nimport { translateChat } from "@/lib/i18n/chat";\n',
        ),
        (
            "list locale",
            '}: ChatMessageListProps) {\n  const scrollRef = useRef<HTMLDivElement>(null);\n',
            '}: ChatMessageListProps) {\n  const { locale } = useI18n();\n  const scrollRef = useRef<HTMLDivElement>(null);\n',
        ),
        (
            "transcript title",
            '              <p className="font-medium">This conversation&rsquo;s messages are no longer available.</p>\n',
            '              <p className="font-medium">{translateChat(locale, "message.transcriptUnavailableTitle")}</p>\n',
        ),
        (
            "transcript body",
            '              <p className="mt-1 text-xs text-muted-foreground">\n                The conversation is still listed, but its transcript was removed from the\n                session store and can&rsquo;t be recovered. You can keep chatting here — new\n                messages will be saved.\n              </p>\n',
            '              <p className="mt-1 text-xs text-muted-foreground">\n                {translateChat(locale, "message.transcriptUnavailable")}\n              </p>\n',
        ),
        ("earlier divider", '                <span>Earlier in this conversation</span>\n', '                <span>{translateChat(locale, "message.earlier")}</span>\n'),
        (
            "start conversation",
            '                Send a message to start the conversation.\n',
            '                {translateChat(locale, "message.startConversation")}\n',
        ),
    ],
    [
        (
            "new message badge",
            r'>\s*↓ New message\s*<',
            '>{translateChat(locale, "message.new")}<',
        ),
    ],
)
