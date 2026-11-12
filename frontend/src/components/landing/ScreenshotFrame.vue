<script setup lang="ts">
import { ExpandIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import ShotMarks from '@/components/content/ShotMarks.vue'

import { type ScreenshotFocus, useScreenshotSource } from '@/composables/useScreenshotSource'
import type { DocMark } from '@/lib/doc-types'

/**
 * A product screenshot in a browser-ish frame, matched to the viewer's theme.
 *
 * The frame is a button: at this size the UI inside is decorative rather than
 * legible, so clicking opens the full-size viewer. Which file gets loaded — and
 * the fallback when a locale is missing one — is handled by
 * `useScreenshotSource`, shared with the lightbox.
 *
 * With `focus` the frame shows one part of the capture, large enough to read,
 * and leaves out the window chrome. The viewer still opens the whole capture.
 *
 * With `marks` the capture carries the numbers the text beside it points at.
 */
const props = defineProps<{
  /** File basename, without the `-light`/`-dark` suffix or extension. */
  name: string
  alt: string
  /** Captured on a phone: 390x844 at twice the density rather than 1440x900. */
  phone?: boolean
  /** The part of the capture to show instead of all of it. */
  focus?: ScreenshotFocus
  marks?: DocMark[]
  /** The mark being pointed at, here or in the text. */
  active?: string | null
}>()

const emit = defineEmits<{ zoom: []; point: [key: string | null] }>()

const { t } = useI18n()
const { src, onError, failed } = useScreenshotSource(() => props.name)
</script>

<template>
  <button
    v-if="!failed"
    type="button"
    class="group relative block w-full cursor-zoom-in overflow-hidden rounded-xl border bg-card text-left shadow-xl ring-1 ring-black/5 transition-shadow hover:shadow-2xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    :aria-label="t('preauth.landing.lightbox.open', { title: alt })"
    @click="emit('zoom')"
  >
    <!-- Window chrome: purely decorative, so it stays out of the a11y tree. -->
    <span
      v-if="!focus"
      aria-hidden="true"
      class="flex items-center gap-1.5 border-b bg-muted/60 px-3 py-2"
    >
      <span class="size-2.5 rounded-full bg-muted-foreground/25" />
      <span class="size-2.5 rounded-full bg-muted-foreground/25" />
      <span class="size-2.5 rounded-full bg-muted-foreground/25" />
    </span>

    <!-- Drawn wider than the frame and shifted, so only the chosen part shows. -->
    <span
      v-if="focus"
      class="relative block overflow-hidden"
      :class="phone ? 'aspect-[4/5]' : 'aspect-[16/10]'"
    >
      <img
        :src="src"
        :alt="alt"
        :width="phone ? 780 : 1440"
        :height="phone ? 1688 : 900"
        loading="lazy"
        decoding="async"
        class="absolute left-0 top-0 h-auto max-w-none"
        :style="{
          width: `${focus.zoom * 100}%`,
          translate: `${-focus.x * 100}% ${-focus.y * 100}%`,
        }"
        @error="onError"
      />
      <!-- The capture goes on past the frame, so its right and lower edge fade
           out instead of ending in a hard cut. -->
      <span
        aria-hidden="true"
        class="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-card to-transparent"
      />
      <span
        aria-hidden="true"
        class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-card to-transparent"
      />
    </span>

    <span v-else class="relative block">
      <!-- The size reserves the space before it loads. -->
      <img
        :src="src"
        :alt="alt"
        :width="phone ? 780 : 1440"
        :height="phone ? 1688 : 900"
        loading="lazy"
        decoding="async"
        class="block h-auto w-full"
        @error="onError"
      />
      <ShotMarks v-if="marks?.length" :marks="marks" :active="active" @point="emit('point', $event)" />
    </span>

    <!-- Affordance, revealed on hover and whenever the frame has focus. Over a
         capture with marks it keeps to a corner, so the marks stay readable. -->
    <span
      aria-hidden="true"
      class="pointer-events-none absolute opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
      :class="
        marks?.length
          ? 'right-2 bottom-2'
          : 'inset-0 flex items-center justify-center bg-black/25'
      "
    >
      <span
        class="flex items-center justify-center rounded-full bg-white/90 shadow-lg"
        :class="marks?.length ? 'size-9' : 'size-12'"
      >
        <ExpandIcon class="size-5 text-neutral-900" />
      </span>
    </span>
  </button>
</template>
