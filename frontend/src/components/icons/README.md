# 平台图标

Custom brand glyphs in the **platform style**. For standard UI glyphs, keep
using [`lucide-react`](https://lucide.dev) — it already matches this style. Only
add a custom icon here when lucide lacks a good brand fit.

## House style

All icons render through `<Icon>` ([Icon.tsx](Icon.tsx)), which locks:

| Property        | Value                          |
| --------------- | ------------------------------ |
| `viewBox`       | `0 0 24 24`                    |
| `stroke`        | `currentColor` (never a fixed colour) |
| `fill`          | `none` (outline icons)         |
| `strokeWidth`   | `1.75`                         |
| `strokeLinecap` | `round`                        |
| `strokeLinejoin`| `round`                        |
| default `size`  | `20` (px)                      |

Colour comes from Tailwind text classes (`text-primary`, `text-muted-foreground`,
…) — the configured application accent colour. Icons are `aria-hidden` by
default; pair with an accessible label on the interactive parent.

## Usage

```tsx
import { SkillIcon, DocIcon } from "@/components/icons";

<SkillIcon className="text-primary" />        {/* 20px, configured accent */}
<DocIcon size={16} className="text-muted-foreground" />
```

## Adding a glyph

1. Draw on the 24×24 grid, **stroke only** (no fills), rounded corners, ~2px
   visual weight. Match the existing glyphs' geometry.
2. Add a thin wrapper in [index.tsx](index.tsx):
   ```tsx
   export function MyIcon(props: IconProps) {
     return <Icon {...props}><path d="…" /></Icon>;
   }
   ```
3. Keep paths minimal — these must read cleanly at 16px.

The current set is `SkillIcon`, `DocIcon`, and `VoiceIcon`. Add other glyphs
when a product component actually needs them.

The application logo is configured through `BRANDING.logo`; the default mark is
`public/images/logo/platform-mark.svg`.
