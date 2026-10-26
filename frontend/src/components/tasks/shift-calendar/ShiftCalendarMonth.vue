<script setup lang="ts">
import { Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

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

defineProps<{
  weeks: CalendarWeek[]
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

const { t } = useI18n()
</script>

<template>
  <div class="overflow-hidden rounded-lg border">
    <!-- Weekday headers -->
    <div class="grid grid-cols-7 border-b bg-muted/50">
      <div
        v-for="name in weekdayNames"
        :key="name"
        class="py-2 text-center text-xs font-medium text-muted-foreground"
      >
        {{ name }}
      </div>
    </div>

    <!-- Week rows -->
    <div
      v-for="(week, weekIdx) in weeks"
      :key="weekIdx"
      class="relative"
      :class="weekIdx > 0 ? 'border-t border-border' : ''"
    >
      <!-- Group bars overlay -->
      <EventBars
        :bars="week.groupBars"
        :hovered-event-id="hoveredEventId"
        :top-offset="28"
        @navigate-event="emit('navigateGroup', $event)"
        @hover="emit('hoverGroup', $event)"
      />

      <!-- Task bars overlay (multi-day tasks) -->
      <TaskBars
        :bars="week.eventBars"
        :hovered-task-id="hoveredTaskId"
        :top-offset="28 + week.barLaneCount * 22"
        @navigate-task="emit('navigateTask', $event)"
        @hover="emit('hoverTask', $event)"
      />

      <!-- Day cells -->
      <div class="grid grid-cols-7">
        <div
          v-for="(day, dayIdx) in week.days"
          :key="dayIdx"
          class="min-h-[72px] p-1 sm:min-h-[100px] sm:p-1.5"
          :class="[
            day.date ? 'bg-background' : 'bg-muted/30',
            dayIdx < 6 ? 'border-r border-border' : '',
          ]"
        >
          <template v-if="day.date">
            <!-- Day number (clickable → day view) -->
            <button
              class="mb-1 flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium hover:bg-muted transition-colors cursor-pointer"
              :class="
                isToday(day.date)
                  ? 'bg-primary text-primary-foreground hover:bg-primary/80'
                  : 'text-muted-foreground'
              "
              @click="emit('selectDay', day)"
            >
              {{ day.date.getDate() }}
            </button>

            <!-- Spacer for event + task bar lanes (desktop) -->
            <div
              v-if="week.barLaneCount + week.eventBarLaneCount > 0"
              class="hidden sm:block"
              :style="{ height: `${(week.barLaneCount + week.eventBarLaneCount) * 22}px` }"
            />

            <!-- Mobile: event dots -->
            <template v-if="day.events.length > 0">
              <div
                v-for="event in day.events.slice(0, 2)"
                :key="'mg-' + event.id"
                class="flex items-center sm:hidden cursor-pointer"
                @click="emit('navigateGroup', event)"
              >
                <span class="h-1.5 w-1.5 rounded-full bg-amber-500" />
              </div>
            </template>

            <!-- Day items (single-day tasks only on desktop; all tasks on mobile) -->
            <div class="space-y-0.5">
              <template v-for="task in day.tasks.slice(0, 3)" :key="'e-' + task.id">
                <div
                  class="flex items-center sm:hidden cursor-pointer"
                  @click="emit('navigateTask', task)"
                >
                  <span
                    class="h-1.5 w-1.5 rounded-full"
                    :class="task.status === 'published' ? 'bg-primary' : 'bg-muted-foreground'"
                  />
                </div>
                <button
                  v-if="!isMultiDayTask(task)"
                  class="hidden w-full truncate rounded px-1 py-0.5 text-left text-xs font-medium transition-opacity hover:opacity-75 sm:block cursor-pointer"
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

              <template
                v-for="booking in day.bookings.slice(
                  0,
                  Math.max(1, 3 - day.tasks.filter((e) => !isMultiDayTask(e)).length),
                )"
                :key="'b-' + booking.id"
              >
                <div
                  class="flex items-center sm:hidden cursor-pointer"
                  @click="emit('navigateBooking', booking)"
                >
                  <span class="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </div>
                <button
                  class="hidden w-full truncate rounded px-1 py-0.5 text-left text-xs font-medium bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 transition-opacity hover:opacity-75 sm:block cursor-pointer"
                  @click="emit('navigateBooking', booking)"
                >
                  {{ booking.title }}
                </button>
              </template>

              <div
                v-if="day.tasks.filter((e) => !isMultiDayTask(e)).length + day.bookings.length > 3"
                class="px-1 text-xs text-muted-foreground cursor-pointer"
              >
                +{{ day.tasks.filter((e) => !isMultiDayTask(e)).length + day.bookings.length - 3 }}
                {{ t('duties.tasks.calendar.more') }}
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
