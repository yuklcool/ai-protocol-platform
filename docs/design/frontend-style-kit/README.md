# Generative UI 页面风格包

从本地 `generative-ui-playground` 的真实 CSS、页面布局及已有截图提取。整体风格可称为 **淡紫 × 薄荷绿的浅色玻璃拟态（Soft Glassmorphism）**。

双击 `index.html` 即可离线预览。这个文件夹可以单独复制，不需要 Node、React、Tailwind、CopilotKit、模型密钥或服务端。

已在 Edge 中验证 `1440px` 桌面、`768px` 平板和 `390px` 手机布局，检查了页面横向溢出、离线字体、鼠标与键盘切换、减少动态效果设置；并目视检查桌面和手机截图。预览截图保存在 `previews/`。

## 文件

| 文件 | 用途 |
| --- | --- |
| `index.html` | 配色、原页面卡片、按钮、标签、表格和侧栏的可交互预览 |
| `theme.css` | 从原版提取的完整设计变量、背景、组件样式，以及普通 CSS 布局类 |
| `fonts.css` | 内嵌 Google Sans Latin 字体，400–700 字重，无需字体 CDN |
| `copilotkit.css` | 可选的原版 CopilotKit 覆盖规则；只有使用该组件库时才加载 |
| `STYLE_PROMPT.md` | 可以直接交给 AI 或设计师的风格描述 |
| `LICENSE` | 原项目 MIT 许可 |
| `FONT-LICENSE.txt` | Google Sans 的 SIL Open Font License 1.1 |

## 视觉规则

### 色彩：背景、文字和操作分开使用

| 角色 | 原版变量或值 |
| --- | --- |
| 淡紫主色 | `--color-lilac: #BEC2FF` |
| 薄荷绿辅色 | `--color-mint: #85E0CE` |
| 页面浅底 | `--color-surface-light: #F7F7F9` |
| 背景渐变终点 | `--color-surface: #DEDEE9` |
| 纯白容器 | `--color-container: #FFFFFF` |
| 主文字 / 次文字 / 辅助文字 | `#010507` / `#57575B` / `#8E8E93` |
| 常规边框 / 浅边框 | `#DBDBE5` / `#EBEBF0` |
| 玻璃表面 / 弱玻璃 / 浓玻璃 | 白色透明度 `70%` / `50%` / `85%` |
| 玻璃边框 | `rgba(255,255,255,.3)` |
| 标题渐变 | `135deg, #9599CC → #1B936F` |
| 主要按钮渐变 | `90deg, #9F8FEF → #7DD3C0` |

标题、按钮、背景光斑用了不同的渐变值，不要统一替换成同一组。蓝、紫、琥珀、绿的图标色用于区分功能类别，不代表成功、错误等业务状态。

### 字体与排版

- 原 `globals.css` 声明 Plus Jakarta Sans，但后加载的 `a2ui-theme.css` 在 `html, body` 覆盖为 **Google Sans**。风格包以最终生效的 Google Sans 为准。
- 内嵌字体只覆盖 Latin 字符；中文由 `Microsoft YaHei`、`PingFang SC` 和系统无衬线字体回退，未打包中文字库。
- 正文 `16px`，行高 `1.6`；说明、标签和表格通常 `14px`；辅助说明 `12px`；卡片标题 `18px / 600`。
- 原版首页标题使用 Tailwind `text-4xl`，实际为桌面 `36px`、手机 `24px`；CSS 中的 `--font-size-4xl: 40px` 是另一个设计变量，不能与实际标题字号混为一谈。
- 数值和代码用系统等宽字体。它是这个说明预览的辅助字体，不是对原版页面字体的替换。

### 布局与间距

- 内容宽度约 `768px`，桌面四周留 `32px`，手机留 `16px`。提取版 `.style-container` 的 `832px` 包含两侧 `32px` 内边距，内宽为 `768px`。
- 顶部标题居中，下面依次为模式切换、功能卡片、比较表格和快捷入口；桌面右侧是助手面板。
- 使用 `4px` 基础间距：`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px`。
- 卡片网格间距 `24px`；小屏一列，`768px` 起两列，`1024px` 起四列。
- 原应用在 `768px` 以下将助手侧栏切换成弹出框。独立预览为便于查看，将示例侧栏排到主内容之后；此布局是预览适配，不是弹出框组件提取。

### 组件配方

| 类名 | 具体效果 |
| --- | --- |
| `.abstract-bg` + `.blob-3` | 固定浅灰渐变底，三个柔焦光斑缓慢漂移 |
| `.glass` / `.glass-card` | 白色 70%、blur 12px、1px 白色 30% 边框、16px 圆角 |
| `.glass-subtle` | 白色 50%、blur 8px、12px 圆角 |
| `.protocol-card` | 玻璃卡片，20px 内边距；悬停上移 4px，显示顶部 3px 紫绿渐变线 |
| `.protocol-card-icon` | 48 × 48px，12px 圆角，类别渐变背景，白色线框图标 |
| `.protocol-tab` / `.active` | 14px、500 字重，激活后纯白底和轻阴影 |
| `.prompt-pill` | 白色 50%、24px 圆角、12 × 16px 内边距，悬停淡紫边框和上移 1px |
| `.style-primary` | 从原页面按钮的 Tailwind 类转译而来，紫绿渐变胶囊按钮 |
| `.comparison-table` | 半透明底、16px 外圆角、16px 单元格内边距、轻分隔线 |

阴影整体克制。原版 `--shadow-glass` 为 `0 4px 30px rgba(0,0,0,.1)`；`.protocol-card` 默认不额外添加这个阴影，悬停才出现较明显阴影。不要把所有容器都加上重阴影。

### 动效

- 光斑：尺寸 `600 / 500 / 400px`，模糊 `80 / 80 / 100px`，透明度 `.6 / .6 / .4`，周期 `25 / 30 / 35s`。
- 小屏光斑缩为 `300 / 250 / 200px`，减少模糊开销。
- 卡片、按钮和标签的状态过渡 `0.2–0.3s ease`；内容本身不漂移。
- 提取版补充了键盘焦点和 `prefers-reduced-motion` 支持；减少动态效果时禁用光斑漂移和悬浮位移。
- 原版显式为浅色主题，本包保持该主题。

## 在新页面复用

将文件夹复制到新项目的静态资源目录，先加载字体，再加载主题：

```html
<link rel="stylesheet" href="./fonts.css">
<link rel="stylesheet" href="./theme.css">

<div class="style-page">
  <div class="abstract-bg" aria-hidden="true">
    <div class="blob-3"></div>
  </div>
  <main class="style-container style-stack">
    <h1 class="style-heading text-gradient">你的页面标题</h1>
    <div class="style-grid">
      <article class="protocol-card">
        <h2>功能名称</h2>
        <p class="style-copy">功能说明</p>
        <button class="prompt-pill" type="button">操作入口</button>
      </article>
    </div>
  </main>
</div>
```

React / Next.js 使用相同 CSS 类；将 `class` 写为 `className`，根据构建器规则导入 CSS，或在页面中链接静态资源。

`theme.css` 是页面级主题，含 `:root`、`body` 和基础控件规则。如果嵌入已有站点的局部区域，需要把这些全局规则迁移到该区域容器；不能保证直接导入后不影响宿主页面。

若使用 CopilotKit，在其官方样式之后额外加载 `copilotkit.css`。该文件保留原项目对第三方选择器的覆盖；最终效果还受 CopilotKit 版本与 DOM 结构影响。独立预览侧栏用普通 HTML/CSS 重现外观，没有复制该组件库的运行时或聊天行为。

## 提取来源与边界

- 设计变量、背景、卡片、标签、表格、动效：`generative-ui-playground/src/app/globals.css`。
- 页面布局和按钮渐变：`generative-ui-playground/src/app/page.tsx`。
- 最终字体及 box-sizing：`generative-ui-playground/src/app/a2ui-theme.css`、`layout.tsx`。
- 上游来源：[CopilotKit Generative UI Playground](https://github.com/CopilotKit/CopilotKit/tree/7b446f86e823e8af4695e78f7a61e800844a9373/examples/showcases/generative-ui-playground)。本地项目已做 A2UI 升级；这里提取的是本地现有视觉样式。
- 字体来自 Google Fonts 的 Google Sans 资源；SIL OFL 许可来自 [Google Fonts / Google Sans](https://github.com/google/fonts/tree/main/ofl/googlesans)。

预览中的说明文字、色板和布局辅助类为本次整理内容。提取对象是应用页面外观；模型动态生成的卡片可使用各自渲染器默认样式，不能仅靠导入本包保证所有生成内容采用同一风格。
