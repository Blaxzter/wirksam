<script setup lang="ts">
/**
 * A row that scrolls sideways: tabs, filter chips, day chips.
 *
 * Built like shadcn's horizontal `ScrollArea`: no native scrollbar (Chrome on
 * Windows draws one with ◂/▸ buttons) but a thin one of its own, and the edge
 * fades out where more of the row is hidden (`scroll-fade-x` in index.css).
 *
 * The bar sits under the row, not over it, so it never covers a tab's
 * underline, and shows while the pointer is over the row. It only exists
 * while the row overflows, and only then does the row make room for it (the
 * `has-` padding): a row that fits keeps its height, and hovering never moves
 * anything. A touch screen has no hover, so there the bar and its room are left
 * out; a swipe and the fading edge do the job.
 *
 * Attributes (class, role, aria-*, listeners) land on the outer box; the row's
 * own layout (gap, alignment, padding) goes in `contentClass`.
 */
import { type HTMLAttributes, computed, onMounted, useTemplateRef } from 'vue'

import { ScrollAreaRoot, ScrollAreaViewport } from 'reka-ui'

import { ScrollBar } from '@/components/ui/scroll-area'

import { cn } from '@/lib/utils'

const props = defineProps<{ contentClass?: HTMLAttributes['class'] }>()

const viewport = useTemplateRef<InstanceType<typeof ScrollAreaViewport>>('viewport')
const scroller = computed<HTMLElement | null>(() => viewport.value?.viewportElement ?? null)

// reka makes the viewport a tab stop, which suits a scrolled text. Here every
// item in the row is a tab stop of its own and scrolls itself into view on
// focus; one more stop on the row around them is noise.
onMounted(() => scroller.value?.setAttribute('tabindex', '-1'))

defineExpose({ scroller })
</script>

<template>
  <ScrollAreaRoot
    type="auto"
    class="group/scroll-row relative min-w-0 pointer-fine:has-[[data-slot=scroll-area-scrollbar]]:pb-2.5"
  >
    <ScrollAreaViewport
      ref="viewport"
      class="scroll-fade-x scroll-px-8 overscroll-x-contain outline-none"
    >
      <div data-slot="scroll-row" :class="cn('flex', props.contentClass)">
        <slot />
      </div>
    </ScrollAreaViewport>
    <ScrollBar
      orientation="horizontal"
      class="h-2 opacity-0 transition-opacity duration-200 group-hover/scroll-row:opacity-100 pointer-coarse:hidden"
    />
  </ScrollAreaRoot>
</template>
