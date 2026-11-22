<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from '@/lib/markdown'

/**
 * Markdown that event admins wrote, shown to members: location and event
 * descriptions.
 *
 * This is the only place `renderMarkdown` output reaches `v-html`; see
 * `lib/markdown.ts` for why that is safe. Renders nothing for empty text.
 * `clamp` cuts it to that many lines, for cards and previews.
 */
const props = defineProps<{
  source: string | null | undefined
  clamp?: 2 | 3
}>()

const html = computed(() => renderMarkdown(props.source))
</script>

<template>
  <div
    v-if="html"
    class="markdown-body"
    :class="{ 'line-clamp-2': clamp === 2, 'line-clamp-3': clamp === 3 }"
    v-html="html"
  />
</template>

<style scoped>
/* No typography plugin in this app, so the few elements markdown produces are
   styled here, in the same spirit as the changelog. */
.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin-bottom: 0.5rem;
  line-height: 1.6;
}
.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(ul) {
  list-style-type: disc;
  padding-left: 1.25rem;
}
.markdown-body :deep(ol) {
  list-style-type: decimal;
  padding-left: 1.25rem;
}
.markdown-body :deep(strong) {
  color: var(--foreground);
  font-weight: 600;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  color: var(--foreground);
  font-weight: 600;
  margin: 0.75rem 0 0.25rem;
}
.markdown-body :deep(a) {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
  overflow-wrap: anywhere;
}
.markdown-body :deep(code) {
  font-size: 0.8125rem;
  background: var(--muted);
  padding: 0.0625rem 0.25rem;
  border-radius: calc(var(--radius) - 4px);
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--border);
  padding-left: 0.75rem;
}
</style>
