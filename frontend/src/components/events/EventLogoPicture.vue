<script setup lang="ts">
import { computed } from 'vue'

import { type LogoSource, eventLogoUrl } from '@/lib/event-appearance'
import { cn } from '@/lib/utils'

/**
 * An event's logo as an image, in the right version for the theme: the
 * version for dark mode where the organisers uploaded one, the logo itself
 * everywhere else. Both are in the page and CSS picks one (`dark:`), so
 * switching the theme swaps them without waiting for a render.
 *
 * Only the image: the box around it (`EventLogo`, the sidebar's wordmark)
 * decides its size and whether dark mode puts it on a white tile. Paper is
 * white whatever the theme, so print always takes the logo itself (the
 * `event-logo-*` classes, see the print styles in index.css).
 */
const props = defineProps<{
  event: LogoSource
  alt?: string
  width?: number | null
  height?: number | null
  class?: string
}>()

const emit = defineEmits<{ error: [] }>()

const light = computed(() => eventLogoUrl(props.event))
const dark = computed(() => eventLogoUrl(props.event, 'dark'))
</script>

<template>
  <img
    v-if="light"
    :src="light"
    :alt="alt ?? ''"
    :width="width ?? undefined"
    :height="height ?? undefined"
    :class="cn('event-logo-light', props.class, dark && 'dark:hidden')"
    data-testid="event-logo-light"
    decoding="async"
    @error="emit('error')"
  />
  <img
    v-if="dark"
    :src="dark"
    :alt="alt ?? ''"
    :width="width ?? undefined"
    :height="height ?? undefined"
    :class="cn('event-logo-dark', props.class, 'hidden dark:block')"
    data-testid="event-logo-dark"
    decoding="async"
    @error="emit('error')"
  />
</template>
