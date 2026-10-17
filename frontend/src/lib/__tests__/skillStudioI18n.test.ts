import { describe, expect, it } from "vitest";
import { SKILL_STUDIO_TRANSLATIONS, translateSkillStudio } from "../i18n/skillStudio";

describe("Skill editor translations", () => {
  it("has matching English and Chinese keys", () => {
    expect(Object.keys(SKILL_STUDIO_TRANSLATIONS.en)).toEqual(Object.keys(SKILL_STUDIO_TRANSLATIONS["zh-CN"]));
  });

  it("explains where Agent settings live in both languages", () => {
    expect(translateSkillStudio("en", "studio.capabilityNotice")).toContain("Root Agent");
    expect(translateSkillStudio("zh-CN", "studio.capabilityNotice")).toContain("Root Agent");
    expect(translateSkillStudio("zh-CN", "builder.invalidFiles")).toContain("不重复");
  });
});
