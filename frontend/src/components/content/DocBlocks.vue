<script setup lang="ts">
import ScreenshotFrame from '@/components/landing/ScreenshotFrame.vue'

import type { DocBlock, DocShot } from '@/lib/doc-types'

/**
 * Text and screenshots of a feature page or guide, in the order they were
 * written. The HTML comes from our own Markdown, rendered at build time with raw
 * HTML switched off (`scripts/docs-plugin.ts`), so `v-html` shows nothing a
 * visitor wrote.
 */
defineProps<{ blocks: DocBlock[] }>()

const emit = defineEmits<{ zoom: [shot: DocShot] }>()
</script>

<template>
  <template v-for="(block, index) in blocks" :key="index">
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="block.type === 'html'" class="doc-text" v-html="block.html" />
    <div v-else class="my-6 flex flex-wrap justify-center gap-4">
      <ScreenshotFrame
        v-for="shot in block.shots"
        :key="shot.name"
        :name="shot.name"
        :alt="shot.alt"
        :phone="shot.phone"
        :class="shot.phone ? 'w-full max-w-60' : ''"
        @zoom="emit('zoom', shot)"
      />
    </div>
  </template>
</template>

<style scoped>
.doc-text :deep(p) {
  margin-bottom: 1rem;
  line-height: 1.7;
  color: var(--muted-foreground);
  text-wrap: pretty;
}

.doc-text :deep(h3) {
  margin-top: 1.75rem;
  margin-bottom: 0.5rem;
  font-size: 1.125rem;
  font-weight: 600;
}

.doc-text :deep(ul),
.doc-text :deep(ol) {
  margin-bottom: 1rem;
  padding-left: 1.25rem;
  color: var(--muted-foreground);
}

.doc-text :deep(ul) {
  list-style-type: disc;
}

.doc-text :deep(ol) {
  list-style-type: decimal;
}

.doc-text :deep(li) {
  margin-bottom: 0.375rem;
  line-height: 1.7;
}

.doc-text :deep(strong) {
  font-weight: 600;
  color: var(--foreground);
}

.doc-text :deep(a) {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.doc-text :deep(blockquote) {
  margin-block: 1.25rem;
  border-left: 3px solid var(--primary);
  border-radius: 0 var(--radius) var(--radius) 0;
  background: color-mix(in oklab, var(--muted) 60%, transparent);
  padding: 0.75rem 1rem;
}

.doc-text :deep(blockquote p:last-child) {
  margin-bottom: 0;
}

.doc-text :deep(code) {
  border-radius: calc(var(--radius) - 2px);
  background: var(--muted);
  padding: 0.1em 0.35em;
  font-size: 0.875em;
  overflow-wrap: anywhere;
  color: var(--foreground);
}

/* Commands keep their line breaks and scroll inside their own box, so a long one
   never widens the page on a phone. */
.doc-text :deep(pre) {
  margin-bottom: 1rem;
  overflow-x: auto;
  border-radius: var(--radius);
  background: var(--muted);
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  line-height: 1.6;
}

.doc-text :deep(pre code) {
  background: none;
  padding: 0;
  font-size: inherit;
  overflow-wrap: normal;
}
</style>
