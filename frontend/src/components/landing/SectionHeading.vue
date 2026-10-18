<script setup lang="ts">
/**
 * Eyebrow + title + optional lede, centred above a section's content.
 *
 * `level` exists so the heading order stays legal: the landing page has a
 * single `h1` in the hero, and every section below it is an `h2`. The content
 * pages have no hero of their own and use this for their `h1`.
 */
withDefaults(
  defineProps<{
    eyebrow?: string
    title: string
    lede?: string
    level?: 'h1' | 'h2' | 'h3'
    /** `hero` inverts the eyebrow for use on the dark band. */
    tone?: 'plain' | 'hero'
  }>(),
  { level: 'h2', tone: 'plain' },
)
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-4 text-center">
    <p
      v-if="eyebrow"
      class="text-xs font-semibold uppercase tracking-[0.18em]"
      :class="tone === 'hero' ? 'text-hero-foreground/80' : 'text-primary'"
    >
      {{ eyebrow }}
    </p>
    <component
      :is="level"
      :data-testid="level === 'h1' ? 'page-heading' : undefined"
      class="text-balance text-3xl font-bold tracking-tight sm:text-4xl"
      :class="tone === 'hero' ? 'text-hero-foreground' : 'text-foreground'"
    >
      {{ title }}
    </component>
    <p
      v-if="lede"
      class="text-pretty text-base leading-relaxed sm:text-lg"
      :class="tone === 'hero' ? 'text-hero-foreground/80' : 'text-muted-foreground'"
    >
      {{ lede }}
    </p>
  </div>
</template>
