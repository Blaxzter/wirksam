<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { EventGroupRead, EventRead } from '@/client/types.gen'

import EventBars from './EventBars.vue'
import GroupBars from './GroupBars.vue'
import type { BookingCalendarItem, CalendarDay, CalendarWeek } from './types'
import { isMultiDayEvent, isToday } from './types'

defineProps<{
  weeks: CalendarWeek[]
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
      <GroupBars
        :bars="week.groupBars"
        :hovered-group-id="hoveredGroupId"
        :top-offset="28"
        @navigate-group="emit('navigateGroup', $event)"
        @hover="emit('hoverGroup', $event)"
      />

      <!-- Event bars overlay (multi-day events) -->
      <EventBars
        :bars="week.eventBars"
        :hovered-event-id="hoveredEventId"
        :top-offset="28 + week.barLaneCount * 22"
        @navigate-event="emit('navigateEvent', $event)"
        @hover="emit('hoverEvent', $event)"
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
              class="mb-1 flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium hover:bg-muted transition-colors"
              :class="
                isToday(day.date)
                  ? 'bg-primary text-primary-foreground hover:bg-primary/80'
                  : 'text-muted-foreground'
              "
              @click="emit('selectDay', day)"
            >
              {{ day.date.getDate() }}
            </button>

            <!-- Spacer for group + event bar lanes (desktop) -->
            <div
              v-if="week.barLaneCount + week.eventBarLaneCount > 0"
              class="hidden sm:block"
              :style="{ height: `${(week.barLaneCount + week.eventBarLaneCount) * 22}px` }"
            />

            <!-- Mobile: group dots -->
            <template v-if="day.groups.length > 0">
              <div
                v-for="group in day.groups.slice(0, 2)"
                :key="'mg-' + group.id"
                class="flex items-center sm:hidden"
                @click="emit('navigateGroup', group)"
              >
                <span class="h-1.5 w-1.5 rounded-full bg-amber-500" />
              </div>
            </template>

            <!-- Day items (single-day events only on desktop; all events on mobile) -->
            <div class="space-y-0.5">
              <template v-for="event in day.events.slice(0, 3)" :key="'e-' + event.id">
                <div class="flex items-center sm:hidden" @click="emit('navigateEvent', event)">
                  <span class="h-1.5 w-1.5 rounded-full" :class="event.status === 'published' ? 'bg-primary' : 'bg-muted-foreground'" />
                </div>
                <button
                  v-if="!isMultiDayEvent(event)"
                  class="hidden w-full truncate rounded px-1 py-0.5 text-left text-xs font-medium transition-opacity hover:opacity-75 sm:block"
                  :class="event.status === 'published' ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'"
                  @click="emit('navigateEvent', event)"
                >
                  {{ event.name }}
                </button>
              </template>

              <template v-for="booking in day.bookings.slice(0, Math.max(1, 3 - day.events.filter(e => !isMultiDayEvent(e)).length))" :key="'b-' + booking.id">
                <div class="flex items-center sm:hidden" @click="emit('navigateBooking', booking)">
                  <span class="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </div>
                <button
                  class="hidden w-full truncate rounded px-1 py-0.5 text-left text-xs font-medium bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 transition-opacity hover:opacity-75 sm:block"
                  @click="emit('navigateBooking', booking)"
                >
                  {{ booking.title }}
                </button>
              </template>

              <div v-if="day.events.filter(e => !isMultiDayEvent(e)).length + day.bookings.length > 3" class="px-1 text-xs text-muted-foreground">
                +{{ day.events.filter(e => !isMultiDayEvent(e)).length + day.bookings.length - 3 }} {{ t('duties.events.calendar.more') }}
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
