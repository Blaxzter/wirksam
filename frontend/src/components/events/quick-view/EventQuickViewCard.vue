<script setup lang="ts">
import { computed, ref } from 'vue'

import { MapPin, Tag, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'

import type { DutySlotRead, EventRead } from '@/client/types.gen'
import { statusVariant } from '@/lib/status'

import WeekDayColumns from './WeekDayColumns.vue'
import type { DayColumn, DaySlotEntry } from './WeekDayColumns.vue'

const props = defineProps<{
  event: EventRead
  slots: DutySlotRead[]
  initialStartDate: Date
  visibleDays?: number
  hideFullSlots?: boolean
}>()

const emit = defineEmits<{
  navigate: [event: EventRead]
  delete: [event: EventRead]
  clickSlot: [slotId: string, event: EventRead]
}>()

const { t } = useI18n()
const authStore = useAuthStore()

const numDays = computed(() => props.visibleDays ?? 5)
const weekOffset = ref(0)
const expanded = ref(false)

const startDate = computed(() => {
  const d = new Date(props.initialStartDate)
  d.setDate(d.getDate() + weekOffset.value * numDays.value)
  return d
})

const days = computed<DayColumn[]>(() => {
  const result: DayColumn[] = []
  const slotsByDate = new Map<string, DaySlotEntry[]>()

  for (const slot of props.slots) {
    const dateStr = slot.date
    if (!slotsByDate.has(dateStr)) slotsByDate.set(dateStr, [])
    slotsByDate.get(dateStr)!.push({
      slotId: slot.id,
      startTime: slot.start_time,
      endTime: slot.end_time,
      currentBookings: slot.current_bookings,
      maxBookings: slot.max_bookings,
      isBookedByMe: slot.is_booked_by_me,
    })
  }

  for (let i = 0; i < numDays.value; i++) {
    const date = new Date(startDate.value)
    date.setDate(date.getDate() + i)
    const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    const daySlots = slotsByDate.get(dateStr) ?? []
    daySlots.sort((a, b) => (a.startTime ?? '').localeCompare(b.startTime ?? ''))
    result.push({ date, dateStr, slots: daySlots })
  }

  return result
})

const totalAvailableSlots = computed(() => {
  return props.slots.filter((s) => {
    if (!s.max_bookings) return true
    return (s.current_bookings ?? 0) < s.max_bookings
  }).length
})
</script>

<template>
  <div class="overflow-hidden rounded-lg border bg-card transition-colors hover:bg-muted/30">
    <div class="flex flex-col md:flex-row md:min-h-[260px]">
      <!-- Top/Left: Event Info -->
      <div
        class="flex cursor-pointer flex-col justify-between border-b p-4 md:w-56 md:shrink-0 md:border-b-0 md:border-r"
        @click="emit('navigate', event)"
      >
        <div class="space-y-2">
          <div class="flex items-start justify-between gap-2">
            <h3 class="text-sm font-semibold leading-tight line-clamp-2 break-words">
              {{ event.name }}
            </h3>
            <Badge
              :variant="statusVariant(event.status)"
              class="shrink-0 text-[10px]"
              v-if="authStore.isAdmin"
            >
              {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
            </Badge>
          </div>

          <p
            v-if="event.description"
            class="text-xs text-muted-foreground line-clamp-2 break-words"
          >
            {{ event.description }}
          </p>

          <div class="space-y-1">
            <div
              v-if="event.location"
              class="flex items-center gap-1 text-xs text-muted-foreground"
            >
              <MapPin class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ event.location }}</span>
            </div>
            <div
              v-if="event.category"
              class="flex items-center gap-1 text-xs text-muted-foreground"
            >
              <Tag class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ event.category }}</span>
            </div>
          </div>
        </div>

        <div class="mt-3 flex items-center justify-between">
          <span class="text-xs text-muted-foreground">
            {{ t('duties.events.quickView.availableSlots', { count: totalAvailableSlots }) }}
          </span>
          <Button
            v-if="authStore.isAdmin"
            variant="ghost"
            size="icon"
            class="h-6 w-6"
            @click.stop="emit('delete', event)"
          >
            <Trash2 class="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      </div>

      <!-- Right: Week Day Columns -->
      <div class="flex min-h-0 flex-1 flex-col p-2">
        <WeekDayColumns
          ref="weekColumns"
          :days="days"
          :visible-days="numDays"
          :expanded="expanded"
          :hide-full-slots="hideFullSlots"
          @previous="weekOffset--"
          @next="weekOffset++"
          @click-slot="(slotId) => emit('clickSlot', slotId, event)"
          @toggle-expand="expanded = !expanded"
        />
      </div>
    </div>
  </div>
</template>
