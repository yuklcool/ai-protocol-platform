import type { Locale, TranslationParams } from "@/lib/i18n";

const en = {
  "signIn.required": "Sign-in required",
  "signIn.openSkill": "You need to sign in to open {skill}.",
  "signIn.openChat": "You need to sign in to open this chat.",
  "signIn.description": "Sessions, document history, and audit traces are scoped to your account. Sign in to continue — you'll land straight back here.",
  "signIn.backHome": "← Back to homepage",

  "context.analyzingOne": "Analyzing {count} document from {folder}",
  "context.analyzingMany": "Analyzing {count} documents from {folder}",
  "context.willProcessOne": "Will process: {file}",
  "context.willProcessMany": "Will process {count} documents on next turn",

  "fallback.cooldownVerb": "unavailable — answered by backup",
  "fallback.failedVerb": "was unavailable — answered by backup",
  "fallback.aria": "Backup model {to} answered because {from} was unavailable",

  "delegation.suggested": "Suggested",
  "delegation.delegated": "Delegated to",
  "delegation.suggestAria": "Suggested handoff to {target}",
  "delegation.delegateAria": "Delegated to {target}",

  "intro.aria": "Assistant introduction",
  "intro.assistant": "Assistant",
  "intro.notStoredAria": "Not stored in session history",
  "intro.notStored": "Intro · not stored",

  "placement.submitted": "Submitted",
  "placement.confirm": "Confirm",
  "placement.actionNeeded": "Action needed",

  "time.justNow": "just now",
  "time.secondsAgo": "{count}s ago",
  "time.minutesAgo": "{count}m ago",
  "time.hoursAgo": "{count}h ago",
  "time.daysAgo": "{count}d ago",

  "sessions.loadingAria": "Loading sessions",
  "sessions.filterAria": "Filter conversations by agent",
  "sessions.allAgents": "All agents",
  "sessions.selectedAgent": "Selected agent",
  "sessions.noneForAgent": "No conversations with this agent",
  "sessions.none": "No previous sessions",
  "sessions.fallbackTitle": "Session {id}",
  "sessions.transcriptLostTitle": "This conversation's messages are no longer available and can't be recovered.",
  "sessions.messagesUnavailable": "Messages unavailable",
  "sessions.historyAria": "Session history",
  "sessions.deleteAria": "Delete {title}",
  "sessions.delete": "Delete",

  "workbench.homeEmpty": "The assistant's results — sources, comparisons, analyses — gather here as it works. Open one to view it.",
  "workbench.results": "Results",
  "workbench.document": "Document",
  "workbench.openDocument": "Open document",
  "workbench.documentDescription": "The document you're working with, alongside the conversation.",
  "workbench.open": "Open ›",
  "workbench.indexDefaultHeading": "Workspace",
  "workbench.indexSummaryOne": "{count} result in this session — open one to view it.",
  "workbench.indexSummaryMany": "{count} results in this session — open one to view it.",

  "shell.result": "Result",
  "shell.assistant": "Assistant",
  "shell.assistantStructuredOutput": "The assistant's structured output for this conversation",
  "shell.resultEmpty": "This result's view will appear here.",
  "shell.resultFallback": "this result",
  "shell.closeResultConfirm": "Close \"{name}\"?\n\nThis removes the result from your workbench and can't be undone. Getting it back means re-running the query or analysis.",
  "shell.workspaceEmpty": "The assistant's structured outputs — clause cards, comparisons, charts — appear here as it works on your question.",
  "shell.home": "Home",
  "shell.workspace": "Workspace",
  "shell.document": "Document",
  "shell.documentEmpty": "Click a document in the sidebar to read it here alongside the conversation.",
  "shell.live": "Live",
  "shell.activity": "Activity",
  "shell.retry": "Try again",
  "shell.dismiss": "Dismiss",
  "shell.you": "You",
  "shell.deleteConversationConfirm": "Delete this conversation? This can't be undone from the UI.",
  "shell.loadingSkill": "Loading skill…",
  "shell.connectingAssistant": "Connecting to assistant… you can start typing in a moment.",
  "shell.tidying": "Tidying up the conversation history — you can keep typing.",
  "shell.messagePlaceholder": "Message…",
  "shell.connectingPlaceholder": "Connecting…",
  "shell.stop": "Stop",
  "shell.send": "Send",
  "shell.library": "Library",
  "shell.yourFiles": "Your files",
  "shell.pastConversations": "Past conversations",
  "shell.startFromDocument": "or start from a document",
  "shell.expandWorkbench": "Expand workbench",
  "shell.collapseWorkbench": "Collapse workbench",
  "shell.workbench": "Workbench",
} as const;

export type ChatTranslationKey = keyof typeof en;

const zhCN = {
  "signIn.required": "需要登录",
  "signIn.openSkill": "登录后才能打开 {skill}。",
  "signIn.openChat": "登录后才能打开此对话。",
  "signIn.description": "会话、文档历史和审计记录都按你的账号隔离。登录后即可继续，并会直接回到当前页面。",
  "signIn.backHome": "← 返回首页",

  "context.analyzingOne": "正在分析来自 {folder} 的 {count} 个文档",
  "context.analyzingMany": "正在分析来自 {folder} 的 {count} 个文档",
  "context.willProcessOne": "将处理：{file}",
  "context.willProcessMany": "下一轮将处理 {count} 个文档",

  "fallback.cooldownVerb": "当前不可用，已由备用模型回答",
  "fallback.failedVerb": "不可用，已由备用模型回答",
  "fallback.aria": "由于 {from} 不可用，已由备用模型 {to} 回答",

  "delegation.suggested": "建议转交给",
  "delegation.delegated": "已转交给",
  "delegation.suggestAria": "建议将问题转交给 {target}",
  "delegation.delegateAria": "已将问题转交给 {target}",

  "intro.aria": "助手介绍",
  "intro.assistant": "助手",
  "intro.notStoredAria": "不会保存到会话历史",
  "intro.notStored": "介绍 · 不保存",

  "placement.submitted": "已提交",
  "placement.confirm": "确认",
  "placement.actionNeeded": "需要操作",

  "time.justNow": "刚刚",
  "time.secondsAgo": "{count} 秒前",
  "time.minutesAgo": "{count} 分钟前",
  "time.hoursAgo": "{count} 小时前",
  "time.daysAgo": "{count} 天前",

  "sessions.loadingAria": "正在加载会话",
  "sessions.filterAria": "按智能体筛选对话",
  "sessions.allAgents": "全部智能体",
  "sessions.selectedAgent": "当前智能体",
  "sessions.noneForAgent": "该智能体暂无历史对话",
  "sessions.none": "暂无历史会话",
  "sessions.fallbackTitle": "会话 {id}",
  "sessions.transcriptLostTitle": "此对话的消息已不可用，且无法恢复。",
  "sessions.messagesUnavailable": "消息不可用",
  "sessions.historyAria": "会话历史",
  "sessions.deleteAria": "删除 {title}",
  "sessions.delete": "删除",

  "workbench.homeEmpty": "助手生成的来源、比较和分析结果会汇总在这里；点击任意结果即可查看。",
  "workbench.results": "结果",
  "workbench.document": "文档",
  "workbench.openDocument": "打开文档",
  "workbench.documentDescription": "在对话旁查看当前正在处理的文档。",
  "workbench.open": "打开 ›",
  "workbench.indexDefaultHeading": "工作台",
  "workbench.indexSummaryOne": "本次会话有 {count} 个结果，点击即可查看。",
  "workbench.indexSummaryMany": "本次会话有 {count} 个结果，点击即可查看。",

  "shell.result": "结果",
  "shell.assistant": "助手",
  "shell.assistantStructuredOutput": "本次对话中助手生成的结构化结果",
  "shell.resultEmpty": "结果视图将在这里显示。",
  "shell.resultFallback": "此结果",
  "shell.closeResultConfirm": "关闭“{name}”？\n\n这会从工作台移除该结果，并且无法撤销。如需恢复，需要重新运行查询或分析。",
  "shell.workspaceEmpty": "助手处理问题时生成的结构化结果（条款卡片、比较结果、图表等）会显示在这里。",
  "shell.home": "首页",
  "shell.workspace": "工作台",
  "shell.document": "文档",
  "shell.documentEmpty": "点击侧边栏中的文档，即可在这里边对话边查看。",
  "shell.live": "实时",
  "shell.activity": "活动",
  "shell.retry": "重试",
  "shell.dismiss": "关闭",
  "shell.you": "你",
  "shell.deleteConversationConfirm": "删除此对话？此操作无法在界面中撤销。",
  "shell.loadingSkill": "正在加载 Skill…",
  "shell.connectingAssistant": "正在连接助手…稍后即可开始输入。",
  "shell.tidying": "正在整理对话历史，你可以继续输入。",
  "shell.messagePlaceholder": "输入消息…",
  "shell.connectingPlaceholder": "连接中…",
  "shell.stop": "停止",
  "shell.send": "发送",
  "shell.library": "文档库",
  "shell.yourFiles": "你的文件",
  "shell.pastConversations": "历史对话",
  "shell.startFromDocument": "或从文档开始",
  "shell.expandWorkbench": "展开工作台",
  "shell.collapseWorkbench": "收起工作台",
  "shell.workbench": "工作台",
} satisfies Record<ChatTranslationKey, string>;

const dictionaries: Record<Locale, Record<ChatTranslationKey, string>> = {
  en,
  "zh-CN": zhCN,
};

export function translateChat(
  locale: Locale,
  key: ChatTranslationKey,
  params: TranslationParams = {},
): string {
  const template = dictionaries[locale][key];
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}

export const CHAT_TRANSLATIONS = dictionaries;
