import { describe, expect, it } from "vitest";

import {
  SKILL_STUDIO_TRANSLATIONS,
  translateSkillStudio,
} from "@/lib/i18n/skillStudio";

describe("Skill Studio i18n", () => {
  it("keeps English and Chinese dictionaries in runtime key parity", () => {
    expect(Object.keys(SKILL_STUDIO_TRANSLATIONS.en)).toEqual(
      Object.keys(SKILL_STUDIO_TRANSLATIONS["zh-CN"]),
    );
  });

  it("preserves English control contracts used by existing Studio tests", () => {
    expect(translateSkillStudio("en", "copilot.apply")).toBe("Apply");
    expect(translateSkillStudio("en", "copilot.dismiss")).toBe("Dismiss");
    expect(translateSkillStudio("en", "delegation.enableAria")).toBe("Enable delegation");
  });

  it("ships Chinese authoring, access and delegation copy", () => {
    expect(translateSkillStudio("zh-CN", "copilot.title")).toBe("创作 Copilot");
    expect(translateSkillStudio("zh-CN", "access.title")).toContain("Skill");
    expect(translateSkillStudio("zh-CN", "delegation.ceiling")).toContain("不会授予额外权限");
  });

  it("preserves important technical references in translated guidance", () => {
    expect(translateSkillStudio("zh-CN", "builder.folderPathHint")).toContain("aitana3/PPAs/longform/");
    expect(translateSkillStudio("zh-CN", "model.pinned")).toContain("eu-strict");
  });
});
