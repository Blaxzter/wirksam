<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { FlaskConicalIcon, LogOutIcon, RotateCcwIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useDialogStore } from '@/stores/dialog'
import { useSandboxStore } from '@/stores/sandbox'

import { Button } from '@/components/ui/button'

import { millisUntil } from '@/lib/server-time'
import { requestTour } from '@/tour/offer'

/**
 * The strip that admits the whole app is make-believe.
 *
 * It has to be honest about two things at once — that this is a demo, and that
 * it is about to disappear — because a visitor who books a shift here and comes
 * back tomorrow to find nothing would rightly conclude the app lost their data.
 *
 * Mounted once in `App.vue`, above every layout, so the countdown is not reset
 * by navigation. That also means it cannot be pushed down by the layouts it
 * covers, hence the offsets below.
 */

/**
 * How far the page is pushed down. Matches the bar's own `h-11`.
 *
 * A constant rather than a measurement because the bar is deliberately one
 * fixed-height line: everything in it truncates instead of wrapping, so there
 * is no second height to discover at runtime.
 */
const BANNER_HEIGHT = '2.75rem'

const { t } = useI18n()
const sandboxStore = useSandboxStore()
const dialogStore = useDialogStore()

const visible = computed(() => sandboxStore.isSandbox)

const roleLabel = computed(() =>
  sandboxStore.role ? t(`sandbox.banner.role.${sandboxStore.role}`) : null,
)

/**
 * The clock, ticked once a second while the bar is up.
 *
 * Only `now` is reactive; the expiry itself comes from the profile. The
 * interval is torn down whenever the bar goes away, so a demo that ends does
 * not leave a timer running for the rest of the session.
 */
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | null = null

// `millisUntil`, not `new Date(iso) - now`: the backend sends naive UTC with no
// offset, which ECMAScript reads as *local* time. East of Greenwich that puts a
// deadline issued a second ago hours in the past, and the bar greets the
// visitor with "this demo has ended" the moment it opens.
const remainingMs = computed(() => millisUntil(sandboxStore.expiresAt, now.value))

const expired = computed(() => remainingMs.value === 0)

/** `mm:ss`, or `h:mm:ss` while there is more than an hour to go. */
const countdown = computed(() => {
  const ms = remainingMs.value
  if (ms === null) return null
  const total = Math.floor(ms / 1000)
  const pad = (value: number) => String(value).padStart(2, '0')
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`
})

function startTicking() {
  if (ticker) return
  now.value = Date.now()
  ticker = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopTicking() {
  if (!ticker) return
  clearInterval(ticker)
  ticker = null
}

/**
 * Make room for a bar that is not in the document flow.
 *
 * `position: fixed` means the layouts underneath know nothing about it, so the
 * space is taken out of the root element instead — one line, undone exactly, no
 * layout component taught about a demo it will usually never see.
 */
function applyOffset() {
  const root = document.documentElement
  root.style.setProperty('--demo-banner-height', BANNER_HEIGHT)
  root.style.paddingTop = BANNER_HEIGHT
  root.dataset.demoBanner = ''
}

function removeOffset() {
  const root = document.documentElement
  root.style.removeProperty('--demo-banner-height')
  root.style.removeProperty('padding-top')
  delete root.dataset.demoBanner
}

watch(
  visible,
  (shown) => {
    if (shown) {
      applyOffset()
      startTicking()
    } else {
      stopTicking()
      removeOffset()
    }
  },
  { immediate: true },
)

// Belt and braces: `visible` flipping false is the ordinary path, but the app
// being torn down (a hot reload, a test unmount) is not, and leaving a stray
// `padding-top` on <html> would outlive this component.
onBeforeUnmount(() => {
  stopTicking()
  removeOffset()
})

/**
 * Ask the guided tour to run again.
 *
 * Through `tour/offer.ts`, which dispatches a window event the engine listens
 * for — not through the engine itself. The import matters: `tour/engine.ts`
 * brings driver.js with it, and this bar is mounted in `App.vue` for every
 * visitor, demo or not. `offer.ts` costs a `ref` and a string.
 */
function restartTour() {
  const track = sandboxStore.role
  if (!track) return
  requestTour(track)
}

async function exit() {
  const confirmed = await dialogStore.confirm({
    title: t('sandbox.exit.title'),
    text: t('sandbox.exit.message'),
    confirmText: t('sandbox.exit.confirm'),
    cancelText: t('sandbox.exit.cancel'),
    variant: 'destructive',
  })
  if (!confirmed) return
  await sandboxStore.exit()
}
</script>

<template>
  <div
    v-if="visible"
    data-testid="sandbox-banner"
    role="region"
    :aria-label="t('sandbox.banner.aria')"
    class="fixed inset-x-0 top-0 z-50 flex h-11 items-center gap-2 bg-primary px-3 text-primary-foreground shadow-sm sm:px-4"
  >
    <FlaskConicalIcon aria-hidden="true" class="size-4 shrink-0" />

    <p class="min-w-0 flex-1 truncate text-sm">
      <span class="font-semibold">{{ t('sandbox.banner.label') }}</span>
      <template v-if="roleLabel">&nbsp;{{ roleLabel }}</template>
      <template v-if="countdown">
        <span aria-hidden="true" class="px-1.5 opacity-60">&middot;</span>
        <span data-testid="sandbox-countdown" class="tabular-nums opacity-90">
          {{
            expired
              ? t('sandbox.banner.expired')
              : t('sandbox.banner.remaining', { time: countdown })
          }}
        </span>
      </template>
    </p>

    <Button
      data-testid="btn-sandbox-tour"
      variant="ghost"
      size="sm"
      class="shrink-0 text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground"
      @click="restartTour"
    >
      <RotateCcwIcon class="size-4" />
      <span class="hidden sm:inline">{{ t('sandbox.banner.restartTour') }}</span>
    </Button>

    <Button
      data-testid="btn-sandbox-exit"
      variant="ghost"
      size="sm"
      :disabled="sandboxStore.exiting"
      class="shrink-0 text-primary-foreground hover:bg-primary-foreground/15 hover:text-primary-foreground"
      @click="exit"
    >
      <LogOutIcon class="size-4" />
      <span class="hidden sm:inline">{{ t('sandbox.banner.exit') }}</span>
    </Button>
  </div>
</template>

<style>
/*
 * Deliberately unscoped: these two selectors reach outside this component.
 *
 * Neither piece of chrome moves with the `padding-top` above, because neither
 * is in the document flow — the desktop sidebar is `fixed inset-y-0 h-svh`, so
 * it would run under the bar and lose its header, and the pre-auth header is
 * `sticky top-0`, which pins to the viewport rather than to the padded root.
 *
 * They are shadcn and layout primitives that every other screen shares, so they
 * are nudged from here, the one place that knows the bar exists, instead of
 * being taught about a demo they will usually never see. Both rules only apply
 * while `data-demo-banner` is on <html>, which this component adds and removes.
 */
html[data-demo-banner] [data-slot='sidebar'] > .fixed {
  top: var(--demo-banner-height);
  height: calc(100svh - var(--demo-banner-height));
}

html[data-demo-banner] header.sticky {
  top: var(--demo-banner-height);
}
</style>
