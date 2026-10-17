import { describe, expect, it } from "vitest";
import { buildSaveBody, emptyDraft, skillToDraft } from "../draft";
import type { Skill } from "@/types/skill";

describe("Skill content saves", () => {
  it("preserves supporting files without resubmitting legacy Agent settings", () => {
    const skill = {
      skillId: "skill-1", name: "analysis", displayName: "Analysis", description: "Inspect data",
      instructions: "Use the reference.", references: { "guide.md": "Reference" },
      assets: { "template.txt": "Template" }, accessControl: { type: "private" },
      skillMetadata: { model: "old-model", toolConfigs: { budget: { enabled: true } } },
      persona: { avatar: "old.png" }, welcome: { introMessage: "Hello" },
    } as unknown as Skill;
    const draft = skillToDraft(skill);
    draft.description = "Updated description";
    const body = buildSaveBody(draft, false);
    expect(body.references).toEqual(skill.references);
    expect(body.assets).toEqual(skill.assets);
    expect(body.description).toBe("Updated description");
    for (const field of ["name", "skillMetadata", "persona", "welcome", "protocols", "shell"]) {
      expect(body).not.toHaveProperty(field);
    }
  });

  it("allows files to be removed explicitly", () => {
    const body = buildSaveBody(emptyDraft(), false);
    expect(body.references).toEqual({});
    expect(body.assets).toEqual({});
  });

  it.each([["", "file.md"], [" guide.md ", "guide.md"]])("rejects ambiguous file names %j", (first, second) => {
    const draft = emptyDraft();
    draft.references = [{ name: first, content: "first" }, { name: second, content: "second" }];
    expect(() => buildSaveBody(draft, true)).toThrow("invalidSkillFiles");
  });

  it("round-trips special property names as ordinary file names", () => {
    const draft = emptyDraft();
    draft.assets = [{ name: "__proto__", content: "Text" }];
    expect(JSON.parse(JSON.stringify(buildSaveBody(draft, true))).assets).toEqual(JSON.parse('{"__proto__":"Text"}'));
  });
});
