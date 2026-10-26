<script setup lang="ts">
import { Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import EventBars from './EventBars.vue'
import TaskBars from './TaskBars.vue'
import type {
  BookingCalendarItem,
  CalendarDay,
  CalendarEvent,
  CalendarTask,
  CalendarWeek,
} from './types'
import { isMultiDayTask, isToday } from './types'

const { t } = useI18n()
const { formatTimeRange } = useFormatters()

defineProps<{
  week: CalendarWeek
  weekdayNames: string[]
  hoveredEventId: string | null
  hoveredTaskId: string | null
}>()

const emit = defineEmits<{
  navigateTask: [task: CalendarTask]
  navigateGroup: [event: CalendarEvent]
  navigateBooking: [booking: BookingCalendarItem]
  hoverGroup: [eventId: string | null]
  hoverTask: [eventId: string | null]
  selectDay: [day: CalendarDay]
}>()
</script>

<template>
  <div class="overflow-hidden rounded-lg border">
    <!-- Weekday headers with dates -->
    <div class="grid grid-cols-7 border-b bg-muted/50">
      <div v-for="(day, idx) in week.days" :key="idx" class="py-2 text-center">
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
      <EventBars
        :bars="week.groupBars"
        :hovered-event-id="hoveredEventId"
        :top-offset="4"
        @navigate-event="emit('navigateGroup', $event)"
        @hover="emit('hoverGroup', $event)"
      />

      <!-- Task bars (multi-day tasks) -->
      <TaskBars
        :bars="week.eventBars"
        :hovered-task-id="hoveredTaskId"
        :top-offset="4 + week.barLaneCount * 22"
        @navigate-task="emit('navigateTask', $event)"
        @hover="emit('hoverTask', $event)"
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
            <!-- Spacer for event + task bar lanes -->
            <div
              v-if="week.barLaneCount + week.eventBarLaneCount > 0"
              class="hidden sm:block"
              :style="{ height: `${(week.barLaneCount + week.eventBarLaneCount) * 22 + 4}px` }"
            />

            <!-- All items (no truncation in week view; multi-day tasks shown as bars) -->
            <div class="space-y-1">
              <template
                v-for="task in day.tasks.filter((e) => !isMultiDayTask(e))"
                :key="'we-' + task.id"
              >
                <button
                  class="w-full truncate rounded px-1.5 py-1 text-left text-xs font-medium transition-opacity hover:opacity-75"
                  :class="
                    task.status === 'published'
                      ? 'bg-primary/15 text-primary'
                      : 'bg-muted text-muted-foreground'
                  "
                  @click="emit('navigateTask', task)"
                >
                  <Lock
                    v-if="task.locked_by_team"
                    class="mr-0.5 inline size-3 align-[-2px]"
                    role="img"
                    :aria-label="t('teamLocks.badge.locked', { name: task.team_name ?? '' })"
                  />{{ task.name }}
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
