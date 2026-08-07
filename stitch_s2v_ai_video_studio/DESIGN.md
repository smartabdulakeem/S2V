---
name: Obsidian Flux
colors:
  surface: '#0f131d'
  surface-dim: '#0f131d'
  surface-bright: '#353944'
  surface-container-lowest: '#0a0e18'
  surface-container-low: '#171b26'
  surface-container: '#1c1f2a'
  surface-container-high: '#262a35'
  surface-container-highest: '#313540'
  on-surface: '#dfe2f1'
  on-surface-variant: '#c7c4d7'
  inverse-surface: '#dfe2f1'
  inverse-on-surface: '#2c303b'
  outline: '#908fa0'
  outline-variant: '#464554'
  surface-tint: '#c0c1ff'
  primary: '#c0c1ff'
  on-primary: '#1000a9'
  primary-container: '#8083ff'
  on-primary-container: '#0d0096'
  inverse-primary: '#494bd6'
  secondary: '#d0bcff'
  on-secondary: '#3c0091'
  secondary-container: '#571bc1'
  on-secondary-container: '#c4abff'
  tertiary: '#4cd7f6'
  on-tertiary: '#003640'
  tertiary-container: '#009eb9'
  on-tertiary-container: '#002f38'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e1e0ff'
  primary-fixed-dim: '#c0c1ff'
  on-primary-fixed: '#07006c'
  on-primary-fixed-variant: '#2f2ebe'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#d0bcff'
  on-secondary-fixed: '#23005c'
  on-secondary-fixed-variant: '#5516be'
  tertiary-fixed: '#acedff'
  tertiary-fixed-dim: '#4cd7f6'
  on-tertiary-fixed: '#001f26'
  on-tertiary-fixed-variant: '#004e5c'
  background: '#0f131d'
  on-background: '#dfe2f1'
  surface-variant: '#313540'
typography:
  display-lg:
    fontFamily: Outfit
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Outfit
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Outfit
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  title-md:
    fontFamily: Outfit
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: '0'
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: '0'
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: '0'
  caption-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.1em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  container-margin: 32px
  gutter: 24px
---

## Brand & Style

The brand personality is cinematic, high-fidelity, and visionary. It targets professional creators, directors, and AI technologists who require an environment that feels as advanced as the generative engines it powers. The UI should evoke a sense of "digital craftsmanship"—where the interface recedes into a sophisticated dark workspace, allowing the video content to take center stage.

The design style is **Modern Obsidian Glassmorphism**. This aesthetic relies on a deep, matte foundation layered with semi-transparent surfaces that mimic frosted glass. The depth is achieved through high-quality backdrop-filter blurs, subtle inner-glow borders, and vibrant "Cosmic" gradients that signify AI processing and energy. The overall feel is futuristic, precise, and premium.

## Colors

The palette is anchored in a deep obsidian spectrum to maximize contrast for video content.

- **Foundational Neutrals:** The base background uses a matte Obsidian (#0B0F19), while secondary surfaces and containers use Slate (#111827).
- **Core Accents:**
  - **Cosmic Indigo (#6366f1):** Used for primary actions and steady-state UI elements.
  - **Electric Violet (#8b5cf6):** Used for AI-generative states, transitions, and magic-enhanced features.
  - **Neon Cyan (#06b6d4):** Used for data-visualization, progress indicators, and precise technical controls.
- **Surface Accents:** High-fidelity glass effects are achieved using semi-transparent white overlays (8-12% opacity) for borders and subtle surface tints.

## Typography

The typography strategy pairs the geometric, modern personality of **Outfit** for headlines with the utilitarian clarity of **Inter** for functional text and UI controls.

- **Hierarchy:** Display and Headline levels use Outfit with tight letter-spacing to feel impactful and cinematic. 
- **Captions:** Technical metadata and small labels should always use the `caption-caps` style, which leverages increased letter-spacing for high legibility at small sizes.
- **Scale:** On mobile devices, headlines scale down by one level to maintain density without sacrificing the bold visual impact.

## Layout & Spacing

This design system utilizes a **12-column fluid grid** for desktop and a **4-column grid** for mobile. The layout philosophy is centered around "Content-First" density.

- **Rhythm:** A strict 4px/8px baseline grid ensures vertical alignment across all technical panels.
- **Floating Panels:** Lateral control panels (Script Editor, Asset Library) should feel like they float above the background, separated by 24px margins from the screen edge.
- **Canvas-Centric:** The central video viewport should always expand to fill the available space, with UI panels collapsing into compact "icon-only" modes on smaller viewports to preserve the workspace.

## Elevation & Depth

Visual hierarchy is established through **Refractive Glassmorphism** rather than traditional drop shadows.

- **Surface Layer 0 (Base):** Matte Obsidian (#0B0F19). No blur.
- **Surface Layer 1 (Floating Cards):** Background blur (backdrop-filter: blur(20px)) with a 10% white tint and a 1px border of `rgba(255, 255, 255, 0.08)`.
- **Surface Layer 2 (Modals/Popovers):** Background blur (40px) with a subtle inner glow on the top edge to simulate light hitting a glass pane.
- **Interactions:** Hover states on glass elements increase the border opacity to 20% and introduce a subtle background "bloom" effect using the Primary Indigo color at 5% opacity.

## Shapes

The shape language is sophisticated and modern, using "Rounded" (0.5rem) as the standard for all structural elements.

- **Cards & Panes:** Use `rounded-lg` (1rem) to create a soft, high-end feel that contrasts with the technical nature of the content.
- **Pills:** All tab indicators, status chips, and primary action buttons use a fully rounded/pill shape to provide a clear interactive affordance.
- **Inputs:** Use standard `rounded` (0.5rem) to maintain a crisp, functional appearance.

## Components

### Buttons
- **Primary:** Features the "Cosmic" gradient. On hover, apply a `box-shadow: 0 0 20px rgba(99, 102, 241, 0.4)` to create a glowing effect.
- **Secondary (Glass):** Transparent background with a `backdrop-filter: blur(10px)` and a white semi-transparent border.

### Inputs & Selectors
- **Fields:** Dark filled background (#111827) with a subtle 1px border. Focus state triggers a Cyan (#06b6d4) outer glow.
- **Aspect Ratio Icons:** Custom geometric icons (16:9, 9:16, 1:1) should be used within pill-shaped selectors to allow quick format switching.

### Cards & Navigation
- **Glass Cards:** Used for the Script Editor and Media Library. Must include a thin white top-border highlight to simulate depth.
- **Tab Indicators:** Active states are represented by a solid pill-shaped background that slides between options using a smooth spring transition.

### Video Timeline
- The timeline should use a transparent background with Neon Cyan for the playhead and Electric Violet for "AI-generated" segments, clearly distinguishing between raw assets and generated content.