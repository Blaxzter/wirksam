<script setup lang="ts">
import type { EventGroupRead, EventRead } from '@/client/types.gen'

import EventBars from './EventBars.vue'
import GroupBars from './GroupBars.vue'
import type { BookingCalendarItem, CalendarDay, CalendarWeek } from './types'
import { formatTimeRange, isMultiDayEvent, isToday } from './types'

defineProps<{
  week: CalendarWeek
  weekdayNames: string[]
  hoveredGroupId: string | null
  hoveredEventId: string | null
}>()

const emit = defineEmits<{
  navigateEvent: [event: EventRead]
  navigateGroup: [group: EventGroupRead]
  navigateBooking: [booking: BookingCalendarItem]
  hoverGroup: [groupId: string | null]
  hoverEvent: [eventId: string | null]
  selectDay: [day: CalendarDay]
}>()
</script>

<template>
  <div class="overflow-hidden rounded-lg border">
    <!-- Weekday headers with dates -->
    <div class="grid grid-cols-7 border-b bg-muted/50">
      <div
        v-for="(day, idx) in week.days"
        :key="idx"
        class="py-2 text-center"
      >
        <div class="text-xs font-medium text-muted-foreground">{{ weekdayNames[idx] }}</div>
        <button
          v-if="day.date"
          class="mx-auto mt-0.5 flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold hover:bg-muted transition-colors"
          :class="isToday(day.date) ? 'bg-primary text-primary-foreground hover:bg-primary/80' : ''"
          @click="emit('selectDay', day)"
        >
          {{ day.date.getDate() }}
        </button>
      </div>
    </div>

    <!-- Single week row -->
    <div class="relative">
      <!-- Group bars -->
      <GroupBars
        :bars="week.groupBars"
        :hovered-group-id="hoveredGroupId"
        :top-offset="4"
        @navigate-group="emit('navigateGroup', $event)"
        @hover="emit('hoverGroup', $event)"
      />

      <!-- Event bars (multi-day events) -->
      <EventBars
        :bars="week.eventBars"
        :hovered-event-id="hoveredEventId"
        :top-offset="4 + week.barLaneCount * 22"
        @navigate-event="emit('navigateEvent', $event)"
        @hover="emit('hoverEvent', $event)"
      />

      <!-- Day columns -->
      <div class="grid grid-cols-7">
        <div
          v-for="(day, dayIdx) in week.days"
          :key="dayIdx"
          class="min-h-[200px] p-1.5 sm:min-h-[280px] sm:p-2"
          :class="[
            day.date ? (isToday(day.date) ? 'bg-primary/5' : 'bg-background') : 'bg-muted/30',
            dayIdx < 6 ? 'border-r border-border' : '',
          ]"
        >
          <template v-if="day.date">
            <!-- Spacer for group + event bar lanes -->
            <div
              v-if="week.barLaneCount + week.eventBarLaneCount > 0"
              class="hidden sm:block"
              :style="{ height: `${(week.barLaneCount + week.eventBarLaneCount) * 22 + 4}px` }"
            />

            <!-- All items (no truncation in week view; multi-day events shown as bars) -->
            <div class="space-y-1">
              <template v-for="event in day.events.filter(e => !isMultiDayEvent(e))" :key="'we-' + event.id">
                <button
                  class="w-full truncate rounded px-1.5 py-1 text-left text-xs font-medium transition-opacity hover:opacity-75"
                  :class="event.status === 'published' ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'"
                  @click="emit('navigateEvent', event)"
                >
                  {{ event.name }}
                </button>
              </template>

              <template v-for="booking in day.bookings" :key="'wb-' + booking.id">
                <button
                  class="w-full rounded px-1.5 py-1 text-left text-xs transition-opacity hover:opacity-75 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                  @click="emit('navigateBooking', booking)"
                >
                  <div class="truncate font-medium">{{ booking.title }}</div>
                  <div v-if="booking.startTime" class="text-[10px] opacity-75">
                    {{ formatTimeRange(booking.startTime, booking.endTime) }}
                  </div>
                </button>
              </template>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
