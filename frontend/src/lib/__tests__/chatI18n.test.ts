import { describe, expect, it } from "vitest";

import { CHAT_TRANSLATIONS, translateChat } from "@/lib/i18n/chat";

describe("Chat i18n", () => {
  it("keeps English and Chinese dictionaries in runtime key parity", () => {
    expect(Object.keys(CHAT_TRANSLATIONS.en)).toEqual(
      Object.keys(CHAT_TRANSLATIONS["zh-CN"]),
    );
  });

  it("interpolates runtime skill, folder, model, result and tool display values", () => {
    expect(translateChat("en", "signIn.openSkill", { skill: "Lighting Analyst" })).toBe(
      "You need to sign in to open Lighting Analyst.",
    );
    expect(
      translateChat("zh-CN", "context.analyzingMany", { count: 3, folder: "合同库" }),
    ).toContain("合同库");
    expect(
      translateChat("zh-CN", "fallback.aria", { from: "model-a", to: "model-b" }),
    ).toContain("model-b");
    expect(
      translateChat("zh-CN", "shell.closeResultConfirm", { name: "比较结果" }),
    ).toContain("比较结果");
    expect(
      translateChat("zh-CN", "typing.using", { tool: "get_document_content" }),
    ).toContain("get_document_content");
    expect(
      translateChat("zh-CN", "notFound.withSlug", { slug: "lighting-analyst" }),
    ).toContain("lighting-analyst");
  });

  it("ships Chinese chat, session, workbench and activity chrome", () => {
    expect(translateChat("zh-CN", "signIn.required")).toBe("需要登录");
    expect(translateChat("zh-CN", "placement.submitted")).toBe("已提交");
    expect(translateChat("zh-CN", "delegation.delegated")).toBe("已转交给");
    expect(translateChat("zh-CN", "intro.notStored")).toContain("不保存");
    expect(translateChat("zh-CN", "sessions.allAgents")).toBe("全部智能体");
    expect(translateChat("zh-CN", "workbench.openDocument")).toBe("打开文档");
    expect(translateChat("zh-CN", "workbench.resizeAria")).toBe("调整工作台宽度");
    expect(translateChat("zh-CN", "shell.send")).toBe("发送");
    expect(translateChat("zh-CN", "activity.running")).toBe("运行中…");
    expect(translateChat("zh-CN", "activity.historySummarised")).toBe("历史已摘要");
  });

  it("ships Chinese permissions, read-only, examples, code and transcript states", () => {
    expect(translateChat("zh-CN", "notFound.eyebrow")).toBe("未找到 Skill");
    expect(translateChat("zh-CN", "readOnly.continue")).toBe("从这里新建会话继续");
    expect(translateChat("zh-CN", "examples.capabilities")).toContain("助手");
    expect(translateChat("zh-CN", "thinking.active")).toBe("思考中…");
    expect(translateChat("zh-CN", "readAloud.read")).toBe("朗读");
    expect(translateChat("zh-CN", "code.copy")).toBe("复制");
    expect(translateChat("zh-CN", "message.earlier")).toBe("本次对话的较早消息");
    expect(translateChat("zh-CN", "message.startConversation")).toBe("发送一条消息开始对话。");
  });
});
