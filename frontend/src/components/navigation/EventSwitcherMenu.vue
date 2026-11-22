<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, Loader2 } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { DrawerViewport } from 'reka-ui'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

import EventLogo from '@/components/events/EventLogo.vue'

import type { EventListResponse, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()

// The complement of `RESPONSIVE_DIALOG_MOBILE_QUERY`, so this component and
// every ResponsiveDialog change shells at the same width.
const isDesktop = useMediaQuery('(min-width: 768px)')

const open = ref(false)
const events = ref<EventRead[]>([])
const loading = ref(false)
const loaded = ref(false)
const switchingId = ref<string | null>(null)

const selectedEventId = computed(() => authStore.selectedEventId)

async function loadEvents() {
  if (loading.value) return
  loading.value = true
  try {
    const res = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: {
        limit: 100,
        date_from: new Date().toISOString().slice(0, 10),
        all_events: true,
      },
    })
    events.value = res.data.items.filter((e) => !e.is_expired)
    loaded.value = true
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

watch(open, (next) => {
  if (next && !loaded.value) {
    void loadEvents()
  }
})

async function selectEvent(event: EventRead) {
  if (event.id === selectedEventId.value || switchingId.value) {
    open.value = false
    return
  }
  switchingId.value = event.id
  try {
    await authStore.setSelectedEvent(event.id)
    toast.success(t('duties.selectEvent.success'))
    open.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    switchingId.value = null
  }
}

function formatRange(event: EventRead): string {
  const fmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })
  return `${fmt.format(new Date(event.start_date))} – ${fmt.format(new Date(event.end_date))}`
}
</script>

<template>
  <Popover v-if="isDesktop" v-model:open="open">
    <PopoverTrigger as-child>
      <slot :open="open" />
    </PopoverTrigger>
    <PopoverContent class="w-72 p-1" align="start" :side-offset="6">
      <div class="px-2 py-1.5 text-xs font-medium text-muted-foreground">
        {{ t('navigation.eventSwitcher.title') }}
      </div>
      <div v-if="loading" class="flex items-center justify-center py-6">
        <Loader2 class="size-4 animate-spin text-muted-foreground" />
      </div>
      <div
        v-else-if="events.length === 0"
        class="px-2 py-4 text-center text-sm text-muted-foreground"
      >
        {{ t('navigation.eventSwitcher.empty') }}
      </div>
      <ul v-else class="max-h-72 overflow-y-auto py-1" role="listbox">
        <li v-for="event in events" :key="event.id">
          <button
            type="button"
            class="flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
            :class="event.id === selectedEventId ? 'bg-accent/50' : ''"
            :disabled="switchingId !== null"
            :data-testid="`event-switcher-option-${event.id}`"
            @click="selectEvent(event)"
          >
            <Check
              class="size-4 shrink-0"
              :class="event.id === selectedEventId ? 'opacity-100' : 'opacity-0'"
            />
            <EventLogo :event="event" size="sm" />
            <div class="min-w-0 flex-1">
              <p class="truncate font-medium">{{ event.name }}</p>
              <p class="text-xs text-muted-foreground">{{ formatRange(event) }}</p>
            </div>
            <Loader2
              v-if="switchingId === event.id"
              class="size-4 shrink-0 animate-spin text-muted-foreground"
            />
          </button>
        </li>
      </ul>
    </PopoverContent>
  </Popover>

  <Drawer v-else v-model:open="open">
    <DrawerTrigger as-child>
      <slot :open="open" />
    </DrawerTrigger>
    <DrawerContent class="max-h-[85vh]">
      <DrawerHeader class="px-4 pt-1 text-left">
        <DrawerTitle>{{ t('navigation.eventSwitcher.title') }}</DrawerTitle>
        <DrawerDescription>{{ t('navigation.eventSwitcher.description') }}</DrawerDescription>
      </DrawerHeader>
      <!--
        `DrawerViewport`, not a plain scroller: it is what lets a drag that
        starts inside the list scroll it instead of dismissing the sheet.
      -->
      <DrawerViewport
        class="overflow-y-auto overscroll-contain px-2 pb-[max(1rem,env(safe-area-inset-bottom))]"
      >
        <div v-if="loading" class="flex items-center justify-center py-8">
          <Loader2 class="size-5 animate-spin text-muted-foreground" />
        </div>
        <div
          v-else-if="events.length === 0"
          class="px-2 py-6 text-center text-sm text-muted-foreground"
        >
          {{ t('navigation.eventSwitcher.empty') }}
        </div>
        <ul v-else role="listbox">
          <li v-for="event in events" :key="event.id">
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded-md px-3 py-3 text-left text-sm transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
              :class="event.id === selectedEventId ? 'bg-accent/50' : ''"
              :disabled="switchingId !== null"
              :data-testid="`event-switcher-option-${event.id}`"
              @click="selectEvent(event)"
            >
              <Check
                class="size-4 shrink-0"
                :class="event.id === selectedEventId ? 'opacity-100' : 'opacity-0'"
              />
              <EventLogo :event="event" size="sm" />
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ event.name }}</p>
                <p class="text-xs text-muted-foreground">{{ formatRange(event) }}</p>
              </div>
              <Loader2
                v-if="switchingId === event.id"
                class="size-4 shrink-0 animate-spin text-muted-foreground"
              />
            </button>
          </li>
        </ul>
      </DrawerViewport>
    </DrawerContent>
  </Drawer>
</template>
