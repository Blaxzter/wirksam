<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ChevronLeftIcon, ChevronRightIcon, XIcon } from '@lucide/vue'
import {
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  VisuallyHidden,
} from 'reka-ui'
import { useI18n } from 'vue-i18n'

import ShotMarks from '@/components/content/ShotMarks.vue'

import { type ScreenshotItem, useScreenshotSource } from '@/composables/useScreenshotSource'

/**
 * Full-screen viewer for the landing page's product screenshots.
 *
 * They are rendered at roughly a third of their captured width in the feature
 * rows, and on a phone the UI in them is unreadable, so each one opens here at
 * full size. Built on Reka's dialog primitives rather than the shadcn wrapper,
 * which is sized and padded for small dialogs and carries a hard-coded English
 * "Close" label.
 *
 * Reka handles the focus trap, Escape, scroll lock, and restoring focus to the
 * frame that opened it.
 */
const props = defineProps<{ items: ScreenshotItem[] }>()

/** Index of the open screenshot; `null` when the viewer is closed. */
const index = defineModel<number | null>('index', { required: true })

const { t } = useI18n()

const open = computed({
  get: () => index.value !== null,
  set: (value: boolean) => {
    if (!value) index.value = null
  },
})

const current = computed(() => (index.value === null ? null : (props.items[index.value] ?? null)))

const { src, onError } = useScreenshotSource(() => current.value?.name ?? '')

/** The mark being pointed at on the open screenshot. */
const active = ref<string | null>(null)

function step(delta: number) {
  if (index.value === null || props.items.length === 0) return
  index.value = (index.value + delta + props.items.length) % props.items.length
}

// Arrow keys walk the gallery. Bound while open only, and removed on close so
// the page's own key handling is untouched the rest of the time.
function onKey(event: KeyboardEvent) {
  if (event.key === 'ArrowRight') step(1)
  else if (event.key === 'ArrowLeft') step(-1)
}

watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('keydown', onKey)
  else window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay
        class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0"
      />
      <DialogContent
        class="fixed inset-0 z-50 flex flex-col items-center justify-center p-4 focus:outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 sm:p-8"
      >
        <VisuallyHidden>
          <DialogTitle>{{ current?.alt ?? t('preauth.landing.lightbox.title') }}</DialogTitle>
          <DialogDescription>{{ t('preauth.landing.lightbox.hint') }}</DialogDescription>
        </VisuallyHidden>

        <button
          type="button"
          class="absolute right-4 top-4 flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          :aria-label="t('preauth.landing.lightbox.close')"
          @click="index = null"
        >
          <XIcon class="size-5" />
        </button>

        <div class="flex w-full max-w-6xl items-center gap-2 sm:gap-4">
          <button
            v-if="items.length > 1"
            type="button"
            class="flex size-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            :aria-label="t('preauth.landing.lightbox.previous')"
            @click="step(-1)"
          >
            <ChevronLeftIcon class="size-5" />
          </button>

          <figure class="flex min-w-0 flex-1 flex-col items-center">
            <!-- As wide as the picture, so the marks sit where they belong. -->
            <span v-if="current" class="relative block max-w-full overflow-hidden rounded-lg">
              <img
                :src="src"
                :alt="current.alt"
                :width="current.phone ? 780 : 1440"
                :height="current.phone ? 1688 : 900"
                class="block h-auto max-h-[75vh] w-auto max-w-full shadow-2xl"
                @error="onError"
              />
              <ShotMarks
                v-if="current.marks?.length"
                :marks="current.marks"
                :active="active"
                @point="active = $event"
              />
            </span>
            <figcaption class="mt-4 text-center text-sm text-white/80">
              {{ current?.caption }}
            </figcaption>
          </figure>

          <button
            v-if="items.length > 1"
            type="button"
            class="flex size-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            :aria-label="t('preauth.landing.lightbox.next')"
            @click="step(1)"
          >
            <ChevronRightIcon class="size-5" />
          </button>
        </div>

        <p v-if="items.length > 1" class="mt-4 text-xs tabular-nums text-white/60">
          {{
            t('preauth.landing.lightbox.counter', {
              current: (index ?? 0) + 1,
              total: items.length,
            })
          }}
        </p>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
