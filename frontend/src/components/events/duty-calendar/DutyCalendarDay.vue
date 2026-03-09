<script setup lang="ts">
import { Clock } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import type { EventGroupRead, EventRead } from '@/client/types.gen'
import Badge from '@/components/ui/badge/Badge.vue'

import type { BookingCalendarItem, CalendarDay } from './types'
import { formatTimeRange, statusVariant } from './types'

defineProps<{
  day: CalendarDay
}>()

const emit = defineEmits<{
  navigateEvent: [event: EventRead]
  navigateGroup: [group: EventGroupRead]
  navigateBooking: [booking: BookingCalendarItem]
}>()

const { t } = useI18n()
</script>

<template>
  <div class="space-y-4">
    <!-- Active groups for this day -->
    <div v-if="day.groups.length > 0" class="flex flex-wrap gap-2">
      <button
        v-for="group in day.groups"
        :key="'dg-' + group.id"
        class="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium bg-amber-500/15 text-amber-700 dark:text-amber-400 hover:bg-amber-500/25 transition-colors"
        @click="emit('navigateGroup', group)"
      >
        {{ group.name }}
      </button>
    </div>

    <!-- Events -->
    <div v-if="day.events.length > 0" class="space-y-2">
      <div
        v-for="event in day.events"
        :key="'de-' + event.id"
        class="flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/50"
        @click="emit('navigateEvent', event)"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-medium truncate">{{ event.name }}</span>
            <Badge :variant="statusVariant(event.status)" class="shrink-0">
              {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
            </Badge>
          </div>
          <p v-if="event.description" class="mt-0.5 text-sm text-muted-foreground truncate">
            {{ event.description }}
          </p>
          <div class="mt-1 text-xs text-muted-foreground">
            {{ t('duties.events.calendar.allDay') }}
            <span v-if="event.location"> · {{ event.location }}</span>
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
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
          <Clock class="h-4 w-4" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium truncate">{{ booking.title }}</div>
          <div class="text-sm text-muted-foreground">
            {{ booking.startTime || booking.endTime
              ? formatTimeRange(booking.startTime, booking.endTime)
              : t('duties.events.calendar.allDay') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-if="day.events.length === 0 && day.bookings.length === 0 && day.groups.length === 0"
      class="py-12 text-center text-muted-foreground"
    >
      {{ t('duties.events.calendar.noItems') }}
    </div>
  </div>
</template>
