<script setup lang="ts">
import { computed, ref } from 'vue'

import { MoonIcon, SunIcon } from '@lucide/vue'
import { useColorMode } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import EventColourPicker from '@/components/events/EventColourPicker.vue'

import { eventColourAttr } from '@/lib/event-appearance'

/**
 * The page about an event's look, tried out in place: the organisers' own
 * pickers (`EventColourPicker`), presets and own colours alike, and a page of
 * the app dressed in what they pick. Nothing is saved.
 *
 * The example carries the colours itself (`event-scope`, see "Event colours"
 * in index.css), so the page around it keeps its own. Light and dark are the
 * page's mode, which the buttons here switch like the one in the header.
 */
const { t } = useI18n()

// A look to start from, so the example shows something of its own at once.
const primary = ref<string | null>('blue')
const secondary = ref<string | null>('yellow')
const base = ref<string | null>('primary')

const mode = useColorMode()

const look = computed(() => {
  const main = eventColourAttr('primary', primary.value)
  const tone = eventColourAttr('base', base.value)
  return {
    'data-event-primary': main,
    'data-event-secondary': eventColourAttr('secondary', secondary.value),
    // A tone that follows the main colour needs one, as in the app.
    'data-event-base': tone === 'primary' && !main ? undefined : tone,
  }
})

const k = (key: string) => t(`preauth.docs.playground.${key}`)
const NAV = ['home', 'tasks', 'bookings', 'vouchers'] as const
</script>

<template>
  <div class="space-y-5 rounded-2xl border bg-card p-4 sm:p-6" data-testid="event-look-playground">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-lg font-semibold">{{ k('title') }}</h3>
        <p class="text-sm text-muted-foreground">{{ k('lede') }}</p>
      </div>
      <div class="flex gap-1 rounded-lg border p-1" role="group" :aria-label="k('mode.label')">
        <Button
          size="sm"
          :variant="mode === 'dark' ? 'ghost' : 'secondary'"
          :aria-pressed="mode !== 'dark'"
          data-testid="playground-light"
          @click="mode = 'light'"
        >
          <SunIcon class="size-4" />
          {{ k('mode.light') }}
        </Button>
        <Button
          size="sm"
          :variant="mode === 'dark' ? 'secondary' : 'ghost'"
          :aria-pressed="mode === 'dark'"
          data-testid="playground-dark"
          @click="mode = 'dark'"
        >
          <MoonIcon class="size-4" />
          {{ k('mode.dark') }}
        </Button>
      </div>
    </div>

    <!-- A page of the app in the picked look. -->
    <div
      v-bind="look"
      class="event-scope overflow-hidden rounded-xl border bg-background text-foreground shadow-sm"
      data-testid="playground-preview"
      aria-hidden="true"
    >
      <div class="grid sm:grid-cols-[10.5rem_1fr]">
        <aside
          class="hidden flex-col gap-1 border-r border-sidebar-border bg-sidebar p-3 text-sm text-sidebar-foreground sm:flex"
        >
          <div class="mb-3 flex items-center gap-2 px-2 py-1">
            <span class="size-6 rounded-full bg-primary" />
            <span class="font-semibold text-primary">{{ k('preview.logo') }}</span>
          </div>
          <span
            v-for="(item, index) in NAV"
            :key="item"
            class="rounded-md px-2 py-1.5"
            :class="{
              'bg-sidebar-primary font-medium text-sidebar-primary-foreground': index === 0,
              'bg-sidebar-accent text-sidebar-accent-foreground': index === 2,
            }"
          >
            {{ k(`preview.nav.${item}`) }}
          </span>
        </aside>

        <div class="min-w-0 space-y-4 p-4 sm:p-5">
          <div>
            <p class="text-xs text-muted-foreground">{{ k('preview.date') }}</p>
            <p class="text-xl font-semibold">{{ k('preview.greeting') }}</p>
          </div>

          <div class="rounded-xl bg-hero p-4 text-hero-foreground">
            <p
              class="flex flex-wrap items-center gap-2 text-xs font-semibold tracking-wide uppercase"
            >
              {{ k('preview.next') }}
              <span
                class="rounded-full bg-hero-chip px-2 py-0.5 tracking-normal text-hero-chip-foreground normal-case"
              >
                {{ k('preview.tomorrow') }}
              </span>
            </p>
            <p class="mt-2 text-3xl font-bold tabular-nums">{{ k('preview.time') }}</p>
            <p class="text-sm opacity-90">{{ k('preview.where') }}</p>
          </div>

          <div class="space-y-3 rounded-xl border bg-card p-3 text-card-foreground">
            <div class="flex items-center justify-between gap-2">
              <p class="text-sm font-semibold">{{ k('preview.open') }}</p>
              <span class="text-sm font-medium text-primary">{{ k('preview.all') }}</span>
            </div>
            <div
              class="flex items-center justify-between gap-2 rounded-md bg-accent px-2 py-1.5 text-sm text-accent-foreground"
            >
              <span class="truncate">{{ k('preview.row1') }}</span>
              <Badge variant="secondary">{{ k('preview.free') }}</Badge>
            </div>
            <div class="flex items-center justify-between gap-2 px-2 text-sm">
              <span class="truncate text-muted-foreground">{{ k('preview.row2') }}</span>
              <span class="shrink-0 text-xs font-medium text-warning">{{
                k('preview.short')
              }}</span>
            </div>
            <div class="flex flex-wrap gap-2 pt-1">
              <Button size="sm" tabindex="-1">{{ k('preview.book') }}</Button>
              <Button size="sm" variant="secondary" tabindex="-1">{{
                k('preview.details')
              }}</Button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="space-y-6">
      <EventColourPicker v-model="primary" kind="primary" id-prefix="playground" />
      <EventColourPicker v-model="secondary" kind="secondary" id-prefix="playground" />
      <EventColourPicker v-model="base" kind="base" :primary="primary" id-prefix="playground" />
    </div>
  </div>
</template>
