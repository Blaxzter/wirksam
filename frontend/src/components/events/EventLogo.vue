<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import EventLogoPicture from '@/components/events/EventLogoPicture.vue'

import {
  eventColourAttr,
  eventInitial,
  eventLogoUrl,
  hasDarkTile,
  isWordmark,
} from '@/lib/event-appearance'
import { cn } from '@/lib/utils'

/**
 * An event's logo in a square tile, or, without one, the first letter of its
 * name on the event's primary colour (muted when it has none), so a list of
 * events can be told apart at a glance either way.
 *
 * In light mode the logo sits straight on the page. In dark mode it shows
 * the version for dark mode where there is one, and sits on a white tile
 * unless the organisers switched that off (`logo_dark_tile`): most logos are
 * drawn for a light page, and a dark wordmark on a transparent ground would
 * vanish on a dark card. It is scaled to fit, never cropped.
 *
 * The tile has the logo's proportions at the size's height, so a wordmark
 * (see `isWordmark`) gets a wide tile rather than a sliver in a square, up to
 * a cap. At `xs` and `sm`, always beside the event's name, a wordmark would be
 * too small to read and gives way to the letter. Callers change the size with
 * a height class (`h-20`), never `size-*`, which would square a wide tile.
 *
 * `fallback: false` renders nothing without a logo, for places that only
 * show one when the organisers have set it (the dashboard, the invitation).
 */
const props = withDefaults(
  defineProps<{
    event: {
      id: string
      name: string
      logo_etag?: string | null
      logo_width?: number | null
      logo_height?: number | null
      logo_dark_etag?: string | null
      logo_dark_tile?: boolean | null
      primary_color?: string | null
    }
    size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
    fallback?: boolean
    /** Alt text; empty by default, since the event's name is nearly always beside it. */
    alt?: string
    class?: string
  }>(),
  { size: 'md', fallback: true, alt: '', class: undefined },
)

const SIZES = {
  xs: 'h-5 rounded text-[0.625rem]',
  sm: 'h-8 rounded-md text-sm',
  md: 'h-10 rounded-md text-base',
  lg: 'h-12 rounded-lg text-lg',
  xl: 'h-16 rounded-xl text-2xl',
} as const

/** How wide a wordmark's tile may grow. */
const WIDE_CAP = { md: 'max-w-40', lg: 'max-w-48', xl: 'max-w-64' } as const

const src = computed(() => eventLogoUrl(props.event))
// A logo that fails to load (deleted a moment ago, offline) shows the letter.
const failed = ref(false)
watch(src, () => (failed.value = false))

const wide = computed(() => isWordmark(props.event))
const tooSmallForWordmark = computed(
  () => wide.value && (props.size === 'xs' || props.size === 'sm'),
)
const showLogo = computed(() => !!src.value && !failed.value && !tooSmallForWordmark.value)
/** The tile's proportions: the logo's for a wordmark, square otherwise. */
const shape = computed(() =>
  wide.value
    ? {
        class: WIDE_CAP[props.size as keyof typeof WIDE_CAP],
        style: { aspectRatio: `${props.event.logo_width} / ${props.event.logo_height}` },
      }
    : { class: 'aspect-square', style: undefined },
)
/** Dark mode's white tile, padded so the logo does not touch its edge. */
const tile = computed(() =>
  hasDarkTile(props.event) ? 'dark:border dark:bg-white dark:p-0.5' : '',
)
const primary = computed(() => eventColourAttr('primary', props.event.primary_color))
</script>

<template>
  <span
    v-if="showLogo"
    data-testid="event-logo"
    :class="
      cn(
        'inline-flex shrink-0 items-center justify-center overflow-hidden',
        tile,
        SIZES[size],
        shape.class,
        props.class,
      )
    "
    :style="shape.style"
  >
    <EventLogoPicture
      :event="event"
      :alt="alt"
      class="size-full object-contain"
      @error="failed = true"
    />
  </span>
  <span
    v-else-if="fallback"
    data-testid="event-logo-fallback"
    :data-event-primary="primary"
    aria-hidden="true"
    :class="
      cn(
        'inline-flex aspect-square shrink-0 items-center justify-center font-semibold select-none',
        primary
          ? 'bg-(--event-primary) text-(--event-primary-foreground)'
          : 'bg-muted text-muted-foreground',
        SIZES[size],
        props.class,
      )
    "
  >
    {{ eventInitial(event.name) }}
  </span>
</template>
