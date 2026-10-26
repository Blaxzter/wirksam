<script setup lang="ts">
import { Clock, Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'

import type { BookingCalendarItem, CalendarDay, CalendarEvent, CalendarTask } from './types'
import { statusVariant } from './types'

const { formatTimeRange } = useFormatters()

defineProps<{
  day: CalendarDay
}>()

const emit = defineEmits<{
  navigateTask: [task: CalendarTask]
  navigateGroup: [event: CalendarEvent]
  navigateBooking: [booking: BookingCalendarItem]
}>()

const { t } = useI18n()
</script>

<template>
  <div class="space-y-4">
    <!-- Active events for this day -->
    <div v-if="day.events.length > 0" class="flex flex-wrap gap-2">
      <button
        v-for="event in day.events"
        :key="'dg-' + event.id"
        class="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium bg-amber-500/15 text-amber-800 dark:text-amber-400 hover:bg-amber-500/25 transition-colors"
        @click="emit('navigateGroup', event)"
      >
        {{ event.name }}
      </button>
    </div>

    <!-- Tasks -->
    <div v-if="day.tasks.length > 0" class="space-y-2">
      <div
        v-for="task in day.tasks"
        :key="'de-' + task.id"
        class="flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/50"
        @click="emit('navigateTask', task)"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-medium truncate">{{ task.name }}</span>
            <Badge
              v-if="task.team_name && task.locked_by_team"
              variant="secondary"
              class="shrink-0"
            >
              <Lock aria-hidden="true" />
              {{ t('teamLocks.badge.only', { name: task.team_name }) }}
            </Badge>
            <Badge :variant="statusVariant(task.status)" class="shrink-0">
              {{ t(`duties.tasks.statuses.${task.status ?? 'draft'}`) }}
            </Badge>
          </div>
          <p v-if="task.description" class="mt-0.5 text-sm text-muted-foreground truncate">
            {{ task.description }}
          </p>
          <div class="mt-1 text-xs text-muted-foreground">
            {{ t('duties.tasks.calendar.allDay') }}
            <span v-if="task.location"> · {{ task.location }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Bookings -->
    <div v-if="day.bookings.length > 0" class="space-y-2">
      <div
        v-for="booking in day.bookings"
        :key="'db-' + booking.id"
        class="flex cursor-pointer items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 transition-colors hover:bg-emerald-500/10"
        @click="emit('navigateBooking', booking)"
      >
        <div
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
        >
          <Clock class="h-4 w-4" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium truncate">{{ booking.title }}</div>
          <div class="text-sm text-muted-foreground">
            {{
              booking.startTime || booking.endTime
                ? formatTimeRange(booking.startTime, booking.endTime)
                : t('duties.tasks.calendar.allDay')
            }}
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-if="day.tasks.length === 0 && day.bookings.length === 0 && day.events.length === 0"
      class="py-12 text-center text-muted-foreground"
    >
      {{ t('duties.tasks.calendar.noItems') }}
    </div>
  </div>
</template>
