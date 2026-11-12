<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from 'vue'

import ScreenshotFrame from '@/components/landing/ScreenshotFrame.vue'

import { shotDevice, shotFile } from '@/lib/doc-shots'
import type { DocBlock, DocDevice, DocShot } from '@/lib/doc-types'

/**
 * Text and screenshots of a feature page or guide, in the order they were
 * written. The HTML comes from our own Markdown, rendered at build time with raw
 * HTML switched off (`scripts/docs-plugin.ts`), so `v-html` shows nothing a
 * visitor wrote.
 *
 * The text names parts of a screenshot with numbered marks, and pointing at a
 * number, in the text or on the screenshot, lights up both.
 */
const props = withDefaults(
  defineProps<{
    blocks: DocBlock[]
    /** Which screenshots to show, where both were taken. */
    device?: DocDevice
  }>(),
  { device: 'desktop' },
)

const emit = defineEmits<{ zoom: [shot: DocShot] }>()

const root = useTemplateRef<HTMLElement>('root')
const active = ref<string | null>(null)

// The numbers in the text are those of the screenshots shown beside it. Those
// come from the computer if the phone has none.
const shown = computed<DocDevice>(() => {
  const shot = props.blocks.flatMap((block) => (block.type === 'shots' ? block.shots : []))[0]
  return shot ? shotDevice(shot, props.device) : props.device
})

const framesOf = (shots: DocShot[]) =>
  shots.map((shot) => ({ shot, device: shotDevice(shot, props.device) }))

// The text is HTML from the build, so its marks are lit up by hand.
watch(active, (key) => {
  for (const mark of root.value?.querySelectorAll<HTMLElement>('.doc-mark') ?? []) {
    mark.classList.toggle('is-active', mark.dataset.mark === key)
  }
})

// Pointing at a number in the text, by mouse or by tapping it.
function onText(event: MouseEvent) {
  const mark = (event.target as HTMLElement).closest<HTMLElement>('.doc-mark')
  active.value = mark?.dataset.mark ?? null
}
</script>

<template>
  <div ref="root" class="doc-blocks" :data-device="shown">
    <template v-for="(block, index) in blocks" :key="index">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div
        v-if="block.type === 'html'"
        class="doc-text"
        @mouseover="onText"
        @mouseleave="active = null"
        v-html="block.html"
      />
      <div v-else class="my-6 flex flex-wrap justify-center gap-4">
        <ScreenshotFrame
          v-for="{ shot, device } in framesOf(block.shots)"
          :key="`${shot.name}-${device}`"
          :name="shotFile(shot.name, device)"
          :alt="shot.alt"
          :phone="device === 'phone'"
          :marks="shot.devices[device]"
          :active="active"
          :class="device === 'phone' ? 'w-full max-w-64' : ''"
          @zoom="emit('zoom', shot)"
          @point="active = $event"
        />
      </div>
    </template>
  </div>
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

/* Bullets and numbers in the page's colour; the shell sets --art. */
.doc-text :deep(li::marker) {
  color: var(--art, var(--primary));
  font-weight: 700;
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
  border-left: 4px solid var(--art, var(--primary));
  border-radius: 0 var(--radius) var(--radius) 0;
  background: color-mix(in oklab, var(--art, var(--primary)) 12%, transparent);
  padding: 0.875rem 1.125rem;
}

.doc-text :deep(blockquote p) {
  color: var(--foreground);
}

.doc-text :deep(blockquote p:last-child) {
  margin-bottom: 0;
}

/* A number in the text for a part of the screenshot beside it. It takes the
   number the screenshot shows, and is left out where that one has no such part. */
.doc-text :deep(.doc-mark) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.375rem;
  height: 1.375rem;
  margin-left: 0.3em;
  padding-inline: 0.25rem;
  border-radius: 9999px;
  background: color-mix(in oklab, var(--art, var(--primary)) 25%, transparent);
  box-shadow: inset 0 0 0 2px var(--art, var(--primary));
  color: var(--foreground);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  vertical-align: 0.1em;
  cursor: default;
  transition:
    scale 0.15s ease,
    background-color 0.15s ease;
}

.doc-text :deep(.doc-mark.is-active) {
  scale: 1.2;
  background: color-mix(in oklab, var(--art, var(--primary)) 55%, transparent);
}

.doc-blocks[data-device='desktop'] .doc-text :deep(.doc-mark)::before {
  content: attr(data-desktop);
}

.doc-blocks[data-device='phone'] .doc-text :deep(.doc-mark)::before {
  content: attr(data-phone);
}

.doc-blocks[data-device='desktop'] .doc-text :deep(.doc-mark:not([data-desktop])),
.doc-blocks[data-device='phone'] .doc-text :deep(.doc-mark:not([data-phone])) {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .doc-text :deep(.doc-mark) {
    transition: none;
  }
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
