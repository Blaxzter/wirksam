<script setup lang="ts">
/**
 * One centred message in place of a guest page's content: a link that leads
 * nowhere, a paused or closed list, a page that is done. The icon carries the
 * mood, the heading says what happened, the text what to do about it.
 */
import { type Component, useTemplateRef } from 'vue'

withDefaults(
  defineProps<{
    icon: Component
    title: string
    text?: string
    /**
     * `h1` when the message is the whole page, `h2` under a list's own title,
     * `p` inside the organisers' preview.
     */
    headingTag?: 'h1' | 'h2' | 'p'
  }>(),
  { text: undefined, headingTag: 'h2' },
)

defineSlots<{
  /** A way on: "try again". */
  default?: () => unknown
}>()

const heading = useTemplateRef<HTMLElement>('heading')

/** Where a page puts focus when it ends here after an action of the visitor's. */
function focus(): void {
  heading.value?.focus({ preventScroll: true })
}

defineExpose({ focus })
</script>

<template>
  <div class="grid justify-items-center gap-3 px-1 py-8 text-center">
    <span
      aria-hidden="true"
      class="grid size-13 place-items-center rounded-full bg-muted text-muted-foreground"
    >
      <component :is="icon" class="size-6" />
    </span>
    <component
      :is="headingTag"
      ref="heading"
      :data-testid="headingTag === 'h1' ? 'page-heading' : undefined"
      :tabindex="headingTag === 'h1' ? -1 : undefined"
      class="text-lg font-semibold text-balance focus:outline-none"
    >
      {{ title }}
    </component>
    <p v-if="text" class="max-w-prose text-sm text-pretty text-muted-foreground">{{ text }}</p>
    <slot />
  </div>
</template>
