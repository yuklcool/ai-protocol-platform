import type { Locale, TranslationParams } from "@/lib/i18n";

const en = {
  "signIn.required": "Sign-in required",
  "signIn.openSkill": "You need to sign in to open {skill}.",
  "signIn.openChat": "You need to sign in to open this chat.",
  "signIn.description": "Sessions, document history, and audit traces are scoped to your account. Sign in to continue — you'll land straight back here.",
  "signIn.backHome": "← Back to homepage",

  "context.analyzingOne": "Analyzing {count} document from {folder}",
  "context.analyzingMany": "Analyzing {count} documents from {folder}",

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
