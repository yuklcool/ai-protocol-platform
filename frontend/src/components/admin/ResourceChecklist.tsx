"use client";

export type ResourceOption = { id: string; label: string };
export function ResourceChecklist({
  label,
  options,
  selected,
  onChange,
  disabled = false,
}: {
  label: string;
  options: ResourceOption[];
  selected: readonly string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const known = new Set(options.map((option) => option.id));
  const rows = [
    ...options,
    ...selected
      .filter((id) => !known.has(id))
      .map((id) => ({ id, label: `${id}（当前不可用，请移除）` })),
  ];
  return (
    <fieldset disabled={disabled} className="space-y-2 glass-panel p-4">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      {rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          暂无可选资源，请先创建 Skill。
        </p>
      )}
      {rows.map((option) => (
        <label key={option.id} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={selected.includes(option.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...selected, option.id]
                  : selected.filter((id) => id !== option.id),
              )
            }
          />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}
