from pathlib import Path

path = Path("frontend/src/components/chat/ChatShell.tsx")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    'import { LatencyHUD } from "@/components/dev/LatencyHUD";\n',
    'import { LatencyHUD } from "@/components/dev/LatencyHUD";\n'
    'import { useI18n } from "@/contexts/I18nContext";\n'
    'import { translateChat } from "@/lib/i18n/chat";\n',
    "imports",
)

replace_once(
    '''const WORKSPACE_RESULT_INDEX_ENTRY = {\n  surfaceId: WORKSPACE_RESULT_TAB_ID,\n  createdAt: 0,\n  kind: "workspace",\n  title: "Assistant",\n  description: "The assistant's structured output for this conversation",\n} as const;\n''',
    '',
    "static workspace result index entry",
)

replace_once(
    '''}) {\n  const workspaceSurface = useSurfaceState("workspace");''',
    '''}) {\n  const { locale } = useI18n();\n  const workspaceSurface = useSurfaceState("workspace");''',
    "WorkbenchPane locale",
)

replace_once(
    '''  const registry = useSurfaceRegistry();\n  const handleCloseResult = useCallback(\n    (surfaceId: string, tabId: string, name: string) => {\n      if (\n        !window.confirm(\n          `Close "${name}"?\\n\\n` +\n            `This removes the result from your workbench and can't be undone. ` +\n            `Getting it back means re-running the query or analysis.`,\n        )\n      ) {\n        return;\n      }''',
    '''  const registry = useSurfaceRegistry();\n  const handleCloseResult = useCallback(\n    (surfaceId: string, tabId: string, name: string) => {\n      if (!window.confirm(translateChat(locale, "shell.closeResultConfirm", { name }))) {\n        return;\n      }''',
    "close result confirmation",
)

replace_once(
    '''    [registry, workbenchTabId, onWorkbenchTabChange],\n  );''',
    '''    [locale, registry, workbenchTabId, onWorkbenchTabChange],\n  );''',
    "close result dependencies",
)

replace_once(
    '''        artifact.title || artifact.kind || "this result",''',
    '''        artifact.title || artifact.kind || translateChat(locale, "shell.resultFallback"),''',
    "artifact fallback name",
)

replace_once(
    '''    [handleCloseResult],\n  );''',
    '''    [handleCloseResult, locale],\n  );''',
    "artifact close dependencies",
)

replace_once(
    '''  const artifactTabs: WorkbenchTab[] = workbenchArtifacts.map((a) => ({\n    id: a.surfaceId,\n    eyebrow: "Result",''',
    '''  const artifactTabs: WorkbenchTab[] = workbenchArtifacts.map((a) => ({\n    id: a.surfaceId,\n    eyebrow: translateChat(locale, "shell.result"),''',
    "artifact eyebrow",
)
replace_once(
    '''    label: a.title || a.kind || "Result",''',
    '''    label: a.title || a.kind || translateChat(locale, "shell.result"),''',
    "artifact label",
)
replace_once(
    '''    emptyBody: a.description || "This result's view will appear here.",''',
    '''    emptyBody: a.description || translateChat(locale, "shell.resultEmpty"),''',
    "artifact empty body",
)

replace_once(
    '''  const workspaceResultTab: WorkbenchTab | null = workspaceSurface?.surface\n    ? {\n        id: WORKSPACE_RESULT_TAB_ID,\n        eyebrow: "Result",\n        label: "Assistant",\n        tooltip: "The assistant's structured output for this conversation",\n        onClose: () => handleCloseResult("workspace", WORKSPACE_RESULT_TAB_ID, "Assistant"),''',
    '''  const workspaceResultTab: WorkbenchTab | null = workspaceSurface?.surface\n    ? {\n        id: WORKSPACE_RESULT_TAB_ID,\n        eyebrow: translateChat(locale, "shell.result"),\n        label: translateChat(locale, "shell.assistant"),\n        tooltip: translateChat(locale, "shell.assistantStructuredOutput"),\n        onClose: () =>\n          handleCloseResult(\n            "workspace",\n            WORKSPACE_RESULT_TAB_ID,\n            translateChat(locale, "shell.assistant"),\n          ),''',
    "workspace result metadata",
)
replace_once(
    '''        emptyBody: "This result's view will appear here.",''',
    '''        emptyBody: translateChat(locale, "shell.resultEmpty"),''',
    "workspace result empty body",
)

replace_once(
    '''  const showIndex = hasArtifacts || Boolean(activeTabId);\n  const homeContent =''',
    '''  const showIndex = hasArtifacts || Boolean(activeTabId);\n  const workspaceResultIndexEntry = {\n    surfaceId: WORKSPACE_RESULT_TAB_ID,\n    createdAt: 0,\n    kind: "workspace",\n    title: translateChat(locale, "shell.assistant"),\n    description: translateChat(locale, "shell.assistantStructuredOutput"),\n  };\n  const homeContent =''',
    "localized workspace result index entry",
)
replace_once(
    '''artifacts={workspaceResultTab ? [...workbenchArtifacts, WORKSPACE_RESULT_INDEX_ENTRY] : workbenchArtifacts}''',
    '''artifacts={workspaceResultTab ? [...workbenchArtifacts, workspaceResultIndexEntry] : workbenchArtifacts}''',
    "workspace index usage",
)
replace_once(
    '''  const workspaceEmptyBody =\n    "The assistant's structured outputs — clause cards, comparisons, charts — appear here as it works on your question.";''',
    '''  const workspaceEmptyBody = translateChat(locale, "shell.workspaceEmpty");''',
    "workspace empty body",
)
replace_once(
    '''    eyebrow: "Home",\n    label: "Workspace",''',
    '''    eyebrow: translateChat(locale, "shell.home"),\n    label: translateChat(locale, "shell.workspace"),''',
    "home tab labels",
)
replace_once(
    '''      label: "Document",''',
    '''      label: translateChat(locale, "shell.document"),''',
    "document tab label",
)
replace_once(
    '''      emptyBody:\n        "Click a document in the sidebar to read it here alongside the conversation.",''',
    '''      emptyBody: translateChat(locale, "shell.documentEmpty"),''',
    "document empty body",
)
replace_once(
    '''      eyebrow: "Live",\n      label: "Activity",''',
    '''      eyebrow: translateChat(locale, "shell.live"),\n      label: translateChat(locale, "shell.activity"),''',
    "activity tab labels",
)

replace_once(
    '''}) {\n  // Rate-limit / quota renders amber ("wait & retry") to visually distinguish a''',
    '''}) {\n  const { locale } = useI18n();\n  // Rate-limit / quota renders amber ("wait & retry") to visually distinguish a''',
    "StreamErrorBanner locale",
)
replace_once(
    '''            Try again''',
    '''            {translateChat(locale, "shell.retry")}''',
    "retry label",
)
replace_once(
    '''          Dismiss''',
    '''          {translateChat(locale, "shell.dismiss")}''',
    "dismiss label",
)

replace_once(
    '''}) {\n  const {\n    sessionId: agentSessionId,''',
    '''}) {\n  const { locale } = useI18n();\n  const {\n    sessionId: agentSessionId,''',
    "ChatShell locale",
)
replace_once(
    '''  const userDisplayName = user.displayName ?? user.email ?? "You";''',
    '''  const userDisplayName = user.displayName ?? user.email ?? translateChat(locale, "shell.you");''',
    "user fallback display name",
)
replace_once(
    '''        !window.confirm(\n          "Delete this conversation? This can't be undone from the UI.",\n        )''',
    '''        !window.confirm(translateChat(locale, "shell.deleteConversationConfirm"))''',
    "delete conversation confirmation",
)
replace_once(
    '''    [sessionId, handleNewSession],\n  );''',
    '''    [locale, sessionId, handleNewSession],\n  );''',
    "delete session dependencies",
)

replace_once(
    '''            {skillMetaLoading\n              ? "Loading skill…"\n              : "Connecting to assistant… you can start typing in a moment."}''',
    '''            {skillMetaLoading\n              ? translateChat(locale, "shell.loadingSkill")\n              : translateChat(locale, "shell.connectingAssistant")}''',
    "connection status",
)
replace_once(
    '''          <span>Tidying up the conversation history — you can keep typing.</span>''',
    '''          <span>{translateChat(locale, "shell.tidying")}</span>''',
    "tidying status",
)
replace_once(
    '''          placeholder={chatReady ? "Message…" : "Connecting…"}''',
    '''          placeholder={\n            chatReady\n              ? translateChat(locale, "shell.messagePlaceholder")\n              : translateChat(locale, "shell.connectingPlaceholder")\n          }''',
    "composer placeholder",
)
replace_once(
    '''            Stop''',
    '''            {translateChat(locale, "shell.stop")}''',
    "stop button",
)
replace_once(
    '''            Send''',
    '''            {translateChat(locale, "shell.send")}''',
    "send button",
)
replace_once(
    '''                title={skillWelcome.bucketBrowser.label || "Library"}''',
    '''                title={skillWelcome.bucketBrowser.label || translateChat(locale, "shell.library")}''',
    "library fallback label",
)
replace_once(
    '''            <SidebarSection title="Your files" persistId="files" defaultOpen={true} bodyClassName="">''',
    '''            <SidebarSection\n              title={translateChat(locale, "shell.yourFiles")}\n              persistId="files"\n              defaultOpen={true}\n              bodyClassName=""\n            >''',
    "your files section",
)
replace_once(
    '''            <SidebarSection title="Past conversations" persistId="conversations" defaultOpen={true}>''',
    '''            <SidebarSection\n              title={translateChat(locale, "shell.pastConversations")}\n              persistId="conversations"\n              defaultOpen={true}\n            >''',
    "past conversations section",
)
replace_once(
    '''                    <span>or start from a document</span>''',
    '''                    <span>{translateChat(locale, "shell.startFromDocument")}</span>''',
    "start from document label",
)
replace_once(
    '''            aria-label="Expand workbench"\n            title="Expand workbench"''',
    '''            aria-label={translateChat(locale, "shell.expandWorkbench")}\n            title={translateChat(locale, "shell.expandWorkbench")}''',
    "expand workbench labels",
)
replace_once(
    '''              Workbench''',
    '''              {translateChat(locale, "shell.workbench")}''',
    "workbench rail label",
)
replace_once(
    '''            aria-label="Collapse workbench"\n            title="Collapse workbench"''',
    '''            aria-label={translateChat(locale, "shell.collapseWorkbench")}\n            title={translateChat(locale, "shell.collapseWorkbench")}''',
    "collapse workbench labels",
)

path.write_text(text, encoding="utf-8")
print(f"Patched {path}")
