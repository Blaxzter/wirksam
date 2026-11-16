<script setup lang="ts">
/**
 * A page's own control row (its tabs, its search and filters) that stays in
 * view right under the app's top bar while the page scrolls.
 *
 * It pins at `--app-header-height`, which `PostAuthHeader` measures and puts on
 * the root. The public pages have no such measurement, so the fallback is their
 * header's fixed 4rem. The demo banner, when shown, sits above both.
 *
 * It bleeds into the content padding (`-mx-4 px-4`), so a pinned bar covers the
 * full column rather than leaving slivers of the list showing at its sides, and
 * it draws a hairline under itself only while it is actually pinned: at rest it
 * should look like the row it always was. For the same reason `-mt-2` takes back
 * the top padding, which only matters once the bar is pinned under the header.
 * (A top margin is free to set: `space-y-*` spaces siblings with the bottom
 * margin of the one before.)
 */
import { type HTMLAttributes, onMounted, ref, useTemplateRef } from 'vue'

import { useEventListener } from '@vueuse/core'

import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const bar = useTemplateRef<HTMLElement>('bar')
const stuck = ref(false)

/**
 * Pinned means the page has scrolled and the bar sits at its sticky offset
 * rather than further down in its natural place. The offset is read back from
 * the computed `top`, so it follows the header's height and the demo banner
 * without being told about either.
 */
function update() {
  const el = bar.value
  if (!el) return
  const pinnedAt = parseFloat(getComputedStyle(el).top) || 0
  stuck.value = window.scrollY > 0 && el.getBoundingClientRect().top <= pinnedAt + 0.5
}

useEventListener(window, 'scroll', update, { passive: true })
useEventListener(window, 'resize', update, { passive: true })
onMounted(update)
</script>

<template>
  <div
    ref="bar"
    data-slot="sticky-page-bar"
    :data-stuck="stuck || undefined"
    :class="
      cn(
        'sticky top-[calc(var(--demo-banner-height,0px)+var(--app-header-height,4rem))] z-20 -mx-4 -mt-2 bg-background px-4 py-2 transition-shadow',
        stuck && 'shadow-[0_1px_0_var(--border)]',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
