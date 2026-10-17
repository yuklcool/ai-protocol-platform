import type { Skill } from "@/types/skill";

export type SkillFile = { name: string; content: string };

/** The content editor never writes legacy Agent configuration. */
export interface StudioDraft {
  skillId?: string;
  ownerId?: string;
  name: string;
  displayName: string;
  description: string;
  instructions: string;
  references: SkillFile[];
  assets: SkillFile[];
  accessControl: Record<string, unknown>;
}

export function emptyDraft(): StudioDraft {
  return {
    name: "", displayName: "", description: "", instructions: "",
    references: [], assets: [], accessControl: { type: "private" },
  };
}

export function skillToDraft(skill: Skill): StudioDraft {
  const files = (value: Record<string, string> = {}) =>
    Object.entries(value).map(([name, content]) => ({ name, content }));
  return {
    skillId: skill.skillId, ownerId: skill.ownerId, name: skill.name,
    displayName: skill.displayName, description: skill.description,
    instructions: skill.instructions, references: files(skill.references),
    assets: files(skill.assets),
    accessControl: skill.accessControl as unknown as Record<string, unknown>,
  };
}

export function buildSaveBody(draft: StudioDraft, isNew: boolean): Record<string, unknown> {
  const files = (entries: SkillFile[]) => {
    const result: Record<string, string> = {};
    for (const entry of entries) {
      const name = entry.name.trim();
      if (!name || Object.prototype.hasOwnProperty.call(result, name)) throw new Error("invalidSkillFiles");
      // defineProperty also handles a literal __proto__ filename safely.
      Object.defineProperty(result, name, { value: entry.content, enumerable: true });
    }
    return result;
  };
  return {
    ...(isNew ? { name: draft.name } : {}),
    displayName: draft.displayName,
    description: draft.description,
    instructions: draft.instructions,
    references: files(draft.references),
    assets: files(draft.assets),
    accessControl: draft.accessControl,
  };
}
