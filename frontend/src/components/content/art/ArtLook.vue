<script setup lang="ts">
/**
 * An event in its own look: the app's window, with a logo at the top of the
 * menu, takes on one look after another as a swatch is picked below it: a
 * main and a second colour, and the base tone of the page and the menu. The
 * colours are the real presets (`data-event-primary`, `data-event-secondary`
 * and `data-event-base`, "Event colours" in index.css), so the drawing shows
 * what an event gets, in light and in dark. The logo sits straight on the
 * menu, as it does in the app.
 *
 * The skins lie on top of each other and take turns. At rest the last one
 * shows, and the ring sits on its swatch.
 */
const skins = [
  { primary: 'blue', secondary: 'yellow', base: 'primary', emblem: 'circle' },
  { primary: 'violet', secondary: 'green', base: 'neutral', emblem: 'diamond' },
  { primary: 'teal', secondary: 'orange', base: 'primary', emblem: 'triangle' },
] as const

/** The swatches under the window; the skins' main colours come first, in their order. */
const swatches = ['blue', 'violet', 'teal', 'orange', 'pink'] as const
const SWATCH_X = (index: number) => 140 + index * 30
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <!-- The window's shadow; each look paints the window itself. -->
    <g class="a-lift">
      <rect x="36" y="36" width="328" height="200" rx="16" class="a-card" />
    </g>

    <g
      v-for="(skin, index) in skins"
      :key="skin.primary"
      :data-event-primary="skin.primary"
      :data-event-secondary="skin.secondary"
      :data-event-base="skin.base"
      :class="`skin skin-${index + 1}`"
    >
      <!-- The page and the menu, in the base tone. -->
      <rect x="36" y="36" width="328" height="200" rx="16" class="page" />
      <path d="M52 36h76v200H52a16 16 0 0 1-16-16V52a16 16 0 0 1 16-16z" class="menu" />

      <!-- The logo, straight on the menu. -->
      <circle v-if="skin.emblem === 'circle'" cx="56" cy="63" r="8" class="primary" />
      <rect
        v-else-if="skin.emblem === 'diamond'"
        x="50"
        y="57"
        width="12"
        height="12"
        rx="2"
        transform="rotate(45 56 63)"
        class="primary"
      />
      <path v-else d="M56 54l9 16H47z" class="primary" />
      <rect x="69" y="57" width="42" height="6" rx="3" class="primary" />
      <rect x="69" y="66" width="28" height="5" rx="2.5" class="secondary" />

      <!-- The selected menu item. -->
      <rect x="46" y="113" width="72" height="18" rx="6" class="primary" />
      <rect x="52" y="119" width="40" height="6" rx="3" class="on-primary" />

      <!-- The large panel, with its countdown chip. -->
      <rect x="144" y="50" width="204" height="72" rx="12" class="hero" />
      <rect x="158" y="66" width="92" height="9" rx="4.5" class="on-hero" />
      <rect x="158" y="84" width="128" height="6" rx="3" class="on-hero faint" />
      <rect x="158" y="98" width="72" height="6" rx="3" class="on-hero faint" />
      <rect x="292" y="62" width="44" height="16" rx="8" class="secondary" />

      <!-- A selected row, and a card in the base tone. -->
      <rect x="144" y="132" width="204" height="24" rx="8" class="soft" />
      <rect x="156" y="141" width="120" height="6" rx="3" class="on-soft" />
      <rect x="144" y="164" width="204" height="24" rx="8" class="paper" />

      <!-- A button and a secondary one. -->
      <rect x="144" y="200" width="76" height="24" rx="8" class="primary" />
      <rect x="160" y="209" width="44" height="6" rx="3" class="on-primary" />
      <rect x="228" y="200" width="76" height="24" rx="8" class="soft" />
      <rect x="244" y="209" width="44" height="6" rx="3" class="on-soft" />
    </g>

    <!-- Lines of text, the same in every look. -->
    <rect x="52" y="98" width="52" height="7" rx="3.5" class="a-line" />
    <rect x="52" y="140" width="46" height="7" rx="3.5" class="a-line" />
    <rect x="52" y="160" width="56" height="7" rx="3.5" class="a-line" />
    <rect x="156" y="173" width="96" height="6" rx="3" class="a-line" />

    <!-- The choice of colours, and the one picked. -->
    <circle
      v-for="(swatch, index) in swatches"
      :key="swatch"
      :data-event-primary="swatch"
      :cx="SWATCH_X(index)"
      cy="266"
      r="9"
      class="primary"
    />
    <circle :cx="SWATCH_X(2)" cy="266" r="13.5" class="ring" />
  </svg>
</template>

<style scoped>
/* The base tone, as the app paints it: the palette's lightness, the base's
   hue, the palette's tint scaled by the base. */
.page {
  fill: oklch(0.945 calc(0.018 * var(--event-base-chroma)) var(--event-base-hue));
  stroke: var(--border);
  stroke-width: 1.5;
}
.menu {
  fill: oklch(0.91 calc(0.022 * var(--event-base-chroma)) var(--event-base-hue));
}
.paper {
  fill: oklch(0.965 calc(0.014 * var(--event-base-chroma)) var(--event-base-hue));
  stroke: oklch(0.87 calc(0.025 * var(--event-base-chroma)) var(--event-base-hue));
  stroke-width: 1.5;
}
.dark .page {
  fill: oklch(0.17 calc(0.01 * var(--event-base-chroma)) var(--event-base-hue));
}
.dark .menu {
  fill: oklch(0.21 calc(0.012 * var(--event-base-chroma)) var(--event-base-hue));
}
.dark .paper {
  fill: oklch(0.21 calc(0.012 * var(--event-base-chroma)) var(--event-base-hue));
  stroke: oklch(0.29 calc(0.014 * var(--event-base-chroma)) var(--event-base-hue));
}
.primary {
  fill: var(--event-primary);
}
.on-primary {
  fill: color-mix(in oklab, var(--event-primary-foreground) 85%, transparent);
}
.hero {
  fill: var(--event-primary-hero);
}
.on-hero {
  fill: color-mix(in oklab, var(--event-primary-hero-foreground) 90%, transparent);
}
.on-hero.faint {
  fill: color-mix(in oklab, var(--event-primary-hero-foreground) 55%, transparent);
}
.secondary {
  fill: var(--event-secondary);
}
.soft {
  fill: var(--event-secondary-soft);
}
.on-soft {
  fill: color-mix(in oklab, var(--event-secondary-soft-foreground) 45%, transparent);
}
.ring {
  fill: none;
  stroke: var(--foreground);
  stroke-width: 2;
  animation: ring 9s cubic-bezier(0.4, 0, 0.2, 1) infinite both;
}

/* Three turns of three seconds, each fading into the next. */
.skin-1 {
  animation: skin-1 9s ease-in-out infinite both;
}
.skin-2 {
  animation: skin-2 9s ease-in-out infinite both;
}
.skin-3 {
  animation: skin-3 9s ease-in-out infinite both;
}
@keyframes skin-1 {
  0%,
  28% {
    opacity: 1;
  }
  36%,
  92% {
    opacity: 0;
  }
  100% {
    opacity: 1;
  }
}
@keyframes skin-2 {
  0%,
  28% {
    opacity: 0;
  }
  36%,
  61% {
    opacity: 1;
  }
  69%,
  100% {
    opacity: 0;
  }
}
@keyframes skin-3 {
  0%,
  61% {
    opacity: 0;
  }
  69%,
  92% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}
/* The ring rests on the third swatch; the turns before it are to its left. */
@keyframes ring {
  0%,
  26% {
    transform: translateX(-60px);
  }
  34%,
  59% {
    transform: translateX(-30px);
  }
  67%,
  92% {
    transform: none;
  }
  100% {
    transform: translateX(-60px);
  }
}
</style>
