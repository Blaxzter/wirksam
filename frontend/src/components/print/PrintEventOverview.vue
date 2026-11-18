<script setup lang="ts">
/**
 * The printed overview of an event: its tasks on one page, with a QR code to
 * the event in the app (`/app/events/<id>`), which offers members its tasks
 * and everyone else the way to join. `ready()` resolves once the code drew.
 */
import { computed } from 'vue'

import { CalendarDays, MapPin, Tag } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import QrCode from '@/components/print/QrCode.vue'

import type { EventRead, TaskRead } from '@/client/types.gen'
import { formatDate } from '@/lib/format'

const props = defineProps<{
  event: EventRead
  tasks: readonly TaskRead[]
}>()

const { t } = useI18n()

const eventUrl = computed(() => `${window.location.origin}/app/events/${props.event.id}`)

let qrDrawn: () => void = () => {}
const qrReady = new Promise<void>((resolve) => (qrDrawn = resolve))

function ready(): Promise<void> {
  return qrReady
}

defineExpose({ ready })
</script>

<template>
  <div class="flex items-start justify-between gap-4">
    <div class="space-y-2 flex-1">
      <h1 class="text-3xl font-bold">{{ event.name }}</h1>
      <p v-if="event.description" class="text-muted-foreground text-lg">
        {{ event.description }}
      </p>
      <p class="text-sm text-muted-foreground flex items-center gap-1">
        <CalendarDays class="h-4 w-4" />
        {{ formatDate(event.start_date) }} – {{ formatDate(event.end_date) }}
      </p>
    </div>
    <div class="shrink-0 text-center space-y-1">
      <QrCode :value="eventUrl" :size="96" @ready="qrDrawn" />
      <p class="text-xs text-muted-foreground">{{ t('print.scanToSignUp') }}</p>
    </div>
  </div>

  <hr class="border-foreground/20" />

  <div class="space-y-4">
    <h2 class="text-xl font-semibold">{{ t('duties.events.detail.tasks') }}</h2>

    <div v-if="tasks.length === 0" class="text-muted-foreground text-sm">
      {{ t('duties.events.detail.tasksEmpty') }}
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="rounded-lg border p-4 space-y-1 print-keep-together"
      >
        <h3 class="font-semibold text-lg">{{ task.name }}</h3>
        <p v-if="task.description" class="text-sm text-muted-foreground">
          {{ task.description }}
        </p>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span class="flex items-center gap-1">
            <CalendarDays class="h-3.5 w-3.5" />
            {{ formatDate(task.start_date) }} – {{ formatDate(task.end_date) }}
          </span>
          <span v-if="task.location" class="flex items-center gap-1">
            <MapPin class="h-3.5 w-3.5" />
            {{ task.location }}
          </span>
          <span v-if="task.category" class="flex items-center gap-1">
            <Tag class="h-3.5 w-3.5" />
            {{ task.category }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
