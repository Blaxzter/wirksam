<script setup lang="ts">
import { ExpandIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useScreenshotSource } from '@/composables/useScreenshotSource'

/**
 * A product screenshot in a browser-ish frame, matched to the viewer's theme.
 *
 * The frame is a button: at this size the UI inside is decorative rather than
 * legible, so clicking opens the full-size viewer. Which file gets loaded — and
 * the fallback when a locale is missing one — is handled by
 * `useScreenshotSource`, shared with the lightbox.
 */
const props = defineProps<{
  /** File basename, without the `-light`/`-dark` suffix or extension. */
  name: string
  alt: string
}>()

const emit = defineEmits<{ zoom: [] }>()

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
    <span aria-hidden="true" class="flex items-center gap-1.5 border-b bg-muted/60 px-3 py-2">
      <span class="size-2.5 rounded-full bg-muted-foreground/25" />
      <span class="size-2.5 rounded-full bg-muted-foreground/25" />
      <span class="size-2.5 rounded-full bg-muted-foreground/25" />
    </span>

    <!-- Every screenshot is 1440x900; the size reserves the space before it loads. -->
    <img
      :src="src"
      :alt="alt"
      width="1440"
      height="900"
      loading="lazy"
      decoding="async"
      class="h-auto w-full"
      @error="onError"
    />

    <!-- Affordance, revealed on hover and whenever the frame has focus. -->
    <span
      aria-hidden="true"
      class="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/25 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
    >
      <span class="flex size-12 items-center justify-center rounded-full bg-white/90 shadow-lg">
        <ExpandIcon class="size-5 text-neutral-900" />
      </span>
    </span>
  </button>
</template>
