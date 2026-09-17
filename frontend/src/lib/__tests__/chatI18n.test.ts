import { describe, expect, it } from "vitest";

import { CHAT_TRANSLATIONS, translateChat } from "@/lib/i18n/chat";

describe("Chat i18n", () => {
  it("keeps English and Chinese dictionaries in runtime key parity", () => {
    expect(Object.keys(CHAT_TRANSLATIONS.en)).toEqual(
      Object.keys(CHAT_TRANSLATIONS["zh-CN"]),
    );
  });

  it("interpolates runtime skill, folder, model and result display values", () => {
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
  });

  it("ships Chinese chat, session and workbench labels", () => {
    expect(translateChat("zh-CN", "signIn.required")).toBe("需要登录");
    expect(translateChat("zh-CN", "placement.submitted")).toBe("已提交");
    expect(translateChat("zh-CN", "delegation.delegated")).toBe("已转交给");
    expect(translateChat("zh-CN", "intro.notStored")).toContain("不保存");
    expect(translateChat("zh-CN", "sessions.allAgents")).toBe("全部智能体");
    expect(translateChat("zh-CN", "workbench.openDocument")).toBe("打开文档");
    expect(translateChat("zh-CN", "shell.send")).toBe("发送");
  });
});
