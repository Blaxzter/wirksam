<script setup lang="ts">
import { computed } from 'vue'

import { useColorMode } from '@vueuse/core'
import { RouterLink } from 'vue-router'

import logoIcon from '@/assets/logo/logo.svg'
import wirksamDarkLogo from '@/assets/logo/wirksam-dark.svg'
import wirksamLightLogo from '@/assets/logo/wirksam-light.svg'

import EventLogo from '@/components/events/EventLogo.vue'
import EventLogoPicture from '@/components/events/EventLogoPicture.vue'

import { eventLogoUrl, hasDarkTile, isWordmark } from '@/lib/event-appearance'

/**
 * The top of the sidebar, a link home. With an event open that has a logo,
 * the logo stands in for the WirkSam wordmark (the footer still names the
 * app): a wordmark on its own, since it carries the name already, and a
 * square-ish mark beside the event's name. Collapsed there is room for a
 * square only, so a wordmark gives way to the event's letter tile.
 *
 * Straight on the sidebar in light mode; in dark mode on a white tile unless
 * the organisers switched it off, like every event logo (see EventLogo.vue).
 */
const props = defineProps<{
  collapsed: boolean
  event?: {
    id: string
    name: string
    logo_etag?: string | null
    logo_width?: number | null
    logo_height?: number | null
    logo_dark_etag?: string | null
    logo_dark_tile?: boolean | null
    primary_color?: string | null
  } | null
}>()

const mode = useColorMode()
const wirksamLogo = computed(() => (mode.value === 'light' ? wirksamDarkLogo : wirksamLightLogo))

const logoUrl = computed(() => eventLogoUrl(props.event))
const wordmark = computed(() => isWordmark(props.event))
/** The event, minus its logo: what the collapsed sidebar shows for a wordmark. */
const letterOnly = computed(() => (props.event ? { ...props.event, logo_etag: null } : null))
</script>

<template>
  <RouterLink
    :to="{ name: 'home' }"
    class="flex items-center gap-2 px-2 py-3 transition-opacity hover:opacity-80"
    :class="{ 'justify-center px-0!': collapsed }"
    :aria-label="collapsed && event && logoUrl ? event.name : undefined"
    data-testid="sidebar-brand"
  >
    <template v-if="event && logoUrl">
      <EventLogo
        v-if="collapsed"
        :event="wordmark ? letterOnly! : event"
        size="sm"
        :alt="event.name"
      />
      <span
        v-else-if="wordmark"
        class="flex h-14 max-w-full items-center rounded-lg"
        :class="{ 'dark:border dark:bg-white dark:px-2 dark:py-1.5': hasDarkTile(event) }"
        data-testid="sidebar-brand-event"
      >
        <EventLogoPicture
          :event="event"
          :alt="event.name"
          :width="event.logo_width"
          :height="event.logo_height"
          class="h-full w-auto max-w-full object-contain"
        />
      </span>
      <span v-else class="flex min-w-0 items-center gap-2.5" data-testid="sidebar-brand-event">
        <EventLogo :event="event" size="lg" />
        <span class="line-clamp-2 text-base leading-tight font-semibold text-sidebar-foreground">
          {{ event.name }}
        </span>
      </span>
    </template>
    <template v-else>
      <img v-if="collapsed" :src="logoIcon" alt="WirkSam" class="size-8" />
      <img v-else :src="wirksamLogo" alt="WirkSam" class="w-auto" data-testid="sidebar-brand-app" />
    </template>
  </RouterLink>
</template>
