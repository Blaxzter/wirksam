<script setup lang="ts">
/**
 * Narrowing a long list down: one task, one day, only the shifts with a place
 * left. Each control shows only when it can narrow anything, so a short list
 * gets none. The filtering itself is the page's (`filterDays`).
 */
import { computed, useId } from 'vue'

import type { AcceptableValue } from 'reka-ui'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

import { ALL_SHIFTS, LONG_DAY, type ShiftFilter } from '@/lib/guest-signup'

const props = defineProps<{
  tasks: readonly { id: string; name: string }[]
  /** The list's days, `YYYY-MM-DD`. */
  dates: readonly string[]
  /** Some shift is full, so "only with a place left" would leave something out. */
  anyFull: boolean
}>()

const filter = defineModel<ShiftFilter>({ required: true })

const { t } = useI18n()
const { formatDateLabel } = useFormatters()
const uid = useId()

const byTask = computed(() => props.tasks.length > 1)
const byDay = computed(() => props.dates.length > 1)
const shown = computed(() => byTask.value || byDay.value || props.anyFull)

/** A Select hands back any value; only a string is a choice. */
function pickOf(value: AcceptableValue): string {
  return typeof value === 'string' && value ? value : ALL_SHIFTS
}

const task = computed<AcceptableValue>({
  get: () => filter.value.task,
  set: (value) => (filter.value = { ...filter.value, task: pickOf(value) }),
})
const day = computed<AcceptableValue>({
  get: () => filter.value.day,
  set: (value) => (filter.value = { ...filter.value, day: pickOf(value) }),
})
const onlyFree = computed<boolean>({
  get: () => filter.value.onlyFree,
  set: (value) => (filter.value = { ...filter.value, onlyFree: value }),
})
</script>

<template>
  <div
    v-if="shown"
    role="group"
    :aria-label="t('guestSignup.list.filters.label')"
    class="flex flex-wrap items-center gap-x-4 gap-y-2"
    data-testid="public-shift-filters"
  >
    <div v-if="byTask" class="min-w-0 flex-1 basis-40 sm:flex-none">
      <Label :for="`${uid}-task`" class="sr-only">{{ t('guestSignup.list.filters.task') }}</Label>
      <Select v-model="task">
        <SelectTrigger
          :id="`${uid}-task`"
          class="h-10 w-full sm:w-52"
          data-testid="public-filter-task"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem :value="ALL_SHIFTS">{{ t('guestSignup.list.filters.allTasks') }}</SelectItem>
          <SelectItem v-for="option in tasks" :key="option.id" :value="option.id">
            {{ option.name }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div v-if="byDay" class="min-w-0 flex-1 basis-40 sm:flex-none">
      <Label :for="`${uid}-day`" class="sr-only">{{ t('guestSignup.list.filters.day') }}</Label>
      <Select v-model="day">
        <SelectTrigger
          :id="`${uid}-day`"
          class="h-10 w-full sm:w-56"
          data-testid="public-filter-day"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem :value="ALL_SHIFTS">{{ t('guestSignup.list.filters.allDays') }}</SelectItem>
          <SelectItem v-for="date in dates" :key="date" :value="date">
            {{ formatDateLabel(date, LONG_DAY) }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div v-if="anyFull" class="flex min-h-10 items-center gap-2">
      <Switch :id="`${uid}-free`" v-model="onlyFree" data-testid="public-filter-free" />
      <Label :for="`${uid}-free`" class="cursor-pointer text-sm font-normal">
        {{ t('guestSignup.list.filters.onlyFree') }}
      </Label>
    </div>
  </div>
</template>
