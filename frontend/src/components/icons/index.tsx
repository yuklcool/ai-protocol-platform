// Aitana custom icon set.
//
// Brand glyphs drawn in the Aitana house style (see ./README.md). Each is a
// thin wrapper over <Icon>, so they inherit the shared 24-grid / 1.75-stroke /
// round-join / currentColor conventions. Use `size` and `className` per icon:
//
//   import { SkillIcon } from "@/components/icons";
//   <SkillIcon className="text-primary" size={18} />
//
// For everything not here, keep using lucide-react — it already matches this
// style. Add a new glyph only when lucide lacks a good brand-fit.

import { Icon, type IconProps } from "./Icon";

export { Icon, type IconProps };

/** Skill / bundle — stacked layers (a skill packages tools + persona). */
export function SkillIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3 21 8 12 13 3 8Z" />
      <path d="M4 12 12 16.5 20 12" />
      <path d="M4 16 12 20.5 20 16" />
    </Icon>
  );
}

/** Document with folded corner + text lines. */
export function DocIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9Z" />
      <path d="M13 3v6h6" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </Icon>
  );
}



/** Voice / read-aloud — speaker with sound waves. */
export function VoiceIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 9v6h3.5L13 19V5L7.5 9Z" />
      <path d="M16.5 8.5a5 5 0 0 1 0 7" />
      <path d="M19 6a8 8 0 0 1 0 12" />
    </Icon>
  );
}
