<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'

import {
  CalendarDate,
  type DateValue,
  getLocalTimeZone,
  today as todayDate,
} from '@internationalized/date'
import { CalendarDays, CalendarX2, ChevronLeft, ChevronRight, X } from 'lucide-vue-next'
import {
  type DateRange,
  RangeCalendarCell,
  RangeCalendarCellTrigger,
  RangeCalendarGrid,
  RangeCalendarGridBody,
  RangeCalendarGridHead,
  RangeCalendarGridRow,
  RangeCalendarHeadCell,
  RangeCalendarHeader,
  RangeCalendarNext,
  RangeCalendarPrev,
  RangeCalendarRoot,
} from 'reka-ui'
import { useDateFormatter } from 'reka-ui'
import { createYear, toDate } from 'reka-ui/date'
import { useI18n } from 'vue-i18n'

import { buttonVariants } from '@/components/ui/button'
import Button from '@/components/ui/button/Button.vue'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    dateFrom: string | null
    dateTo: string | null
    /** Set of ISO date strings (YYYY-MM-DD) to show dot indicators on */
    markedDays?: Set<string>
    /** Label when no range is selected */
    defaultLabel?: string
    /** Label for the reset button */
    resetLabel?: string
  }>(),
  {
    markedDays: () => new Set<string>(),
    defaultLabel: undefined,
    resetLabel: undefined,
  },
)

const emit = defineEmits<{
  'update:dateFrom': [value: string | null]
  'update:dateTo': [value: string | null]
  /** Emitted when the visible month changes — parent can fetch marked days for this range */
  'update:visibleMonth': [range: { from: string; to: string }]
}>()

const { t, locale } = useI18n()

const tz = getLocalTimeZone()
const todayVal = todayDate(tz)

function toCalendarDate(iso: string): CalendarDate {
  const [y, m, d] = iso.split('-').map(Number)
  return new CalendarDate(y, m, d)
}

function toIso(date: DateValue): string {
  return `${date.year}-${String(date.month).padStart(2, '0')}-${String(date.day).padStart(2, '0')}`
}

// Internal range model synced with props
// Use shallowRef to preserve class identity (CalendarDate etc.) which ref's deep unwrap would strip
const rangeValue = shallowRef<DateRange | undefined>(
  props.dateFrom
    ? {
        start: toCalendarDate(props.dateFrom),
        end: props.dateTo ? toCalendarDate(props.dateTo) : toCalendarDate(props.dateFrom),
      }
    : undefined,
)

const placeholder = shallowRef<DateValue>(props.dateFrom ? toCalendarDate(props.dateFrom) : todayVal)

const formatter = useDateFormatter(locale.value)

// Emit when range changes
function handleRangeUpdate(range: DateRange) {
  rangeValue.value = range
  if (range.start && range.end) {
    emit('update:dateFrom', toIso(range.start))
    emit('update:dateTo', toIso(range.end))
  }
}

function clearSelection() {
  rangeValue.value = undefined
  placeholder.value = todayVal
  emit('update:dateFrom', null)
  emit('update:dateTo', null)
}

// Emit visible month range when placeholder changes
function emitVisibleMonth(date: DateValue) {
  const year = date.year
  const month = date.month
  const from = `${year}-${String(month).padStart(2, '0')}-01`
  const lastDay = new Date(year, month, 0).getDate()
  const to = `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`
  emit('update:visibleMonth', { from, to })
}

watch(placeholder, (val) => emitVisibleMonth(val as DateValue), { immediate: true })

function isMarked(date: DateValue): boolean {
  return props.markedDays.has(toIso(date))
}

function isEndpoint(date: DateValue): boolean {
  if (!rangeValue.value) return false
  const { start, end } = rangeValue.value
  return (!!start && date.compare(start as DateValue) === 0) || (!!end && date.compare(end as DateValue) === 0)
}

// Display label
const displayLabel = computed(() => {
  const fallback = props.defaultLabel ?? t('duties.events.filters.fromToday')
  if (!props.dateFrom) return fallback
  const fromDate = new Date(props.dateFrom + 'T00:00:00')
  const fromStr = fromDate.toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
  if (!props.dateTo || props.dateTo === props.dateFrom) {
    return t('duties.events.filters.fromDate', { date: fromStr })
  }
  const toDate = new Date(props.dateTo + 'T00:00:00')
  const toStr = toDate.toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
  return `${fromStr} — ${toStr}`
})

const hasValue = computed(() => props.dateFrom !== null)
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <Button variant="outline" size="sm" class="justify-start text-left font-normal">
        <CalendarDays class="h-4 w-4 shrink-0" />
        <span class="truncate">{{ displayLabel }}</span>
        <button
          v-if="hasValue"
          class="ml-auto rounded-sm p-0.5 hover:bg-accent"
          @click.stop="clearSelection"
        >
          <X class="h-3 w-3" />
        </button>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-auto p-0" align="start">
      <RangeCalendarRoot
        v-slot="{ grid, weekDays, date }"
        v-model:placeholder="placeholder"
        :model-value="rangeValue"
        :locale="locale"
        weekday-format="short"
        :week-starts-on="1"
        class="p-3"
        @update:model-value="handleRangeUpdate"
      >
        <RangeCalendarHeader class="relative flex w-full items-center justify-between pt-1">
          <RangeCalendarPrev
            :class="
              cn(
                buttonVariants({ variant: 'outline' }),
                'h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100',
              )
            "
          >
            <ChevronLeft class="size-4" />
          </RangeCalendarPrev>
          <!-- Month + year selectors -->
          <div class="flex items-center gap-1">
            <div class="**:data-[slot=native-select-icon]:right-1">
              <div class="relative">
                <div
                  class="absolute inset-0 flex h-full items-center text-sm pl-2 pointer-events-none"
                >
                  {{ formatter.custom(toDate(date), { month: 'short' }) }}
                </div>
                <NativeSelect
                  class="text-xs h-8 pr-6 pl-2 text-transparent relative"
                  @change="
                    (e: Event) => {
                      placeholder = placeholder.set({
                        month: Number((e?.target as any)?.value),
                      })
                    }
                  "
                >
                  <NativeSelectOption
                    v-for="month in createYear({ dateObj: date })"
                    :key="month.toString()"
                    :value="month.month"
                    :selected="date.month === month.month"
                  >
                    {{ formatter.custom(toDate(month), { month: 'short' }) }}
                  </NativeSelectOption>
                </NativeSelect>
              </div>
            </div>
            {{ formatter.custom(toDate(date), { year: 'numeric' }) }}
          </div>
          <RangeCalendarNext
            :class="
              cn(
                buttonVariants({ variant: 'outline' }),
                'h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100',
              )
            "
          >
            <ChevronRight class="size-4" />
          </RangeCalendarNext>
        </RangeCalendarHeader>

        <div class="mt-4">
          <RangeCalendarGrid v-for="month in grid" :key="month.value.toString()">
            <RangeCalendarGridHead>
              <RangeCalendarGridRow>
                <RangeCalendarHeadCell
                  v-for="day in weekDays"
                  :key="day"
                  class="w-8 rounded-md text-[0.8rem] font-normal text-muted-foreground"
                >
                  {{ day }}
                </RangeCalendarHeadCell>
              </RangeCalendarGridRow>
            </RangeCalendarGridHead>
            <RangeCalendarGridBody>
              <RangeCalendarGridRow
                v-for="(weekDates, index) in month.rows"
                :key="`week-${index}`"
                class="mt-2 w-full"
              >
                <RangeCalendarCell
                  v-for="weekDate in weekDates"
                  :key="weekDate.toString()"
                  :date="weekDate"
                  class="relative p-px text-center text-sm data-[highlighted]:bg-accent data-[selection-start]:rounded-l-md data-[selection-end]:rounded-r-md"
                >
                  <RangeCalendarCellTrigger
                    :day="weekDate"
                    :month="month.value"
                    :class="
                      cn(
                        buttonVariants({ variant: 'ghost' }),
                        'size-8 p-0 font-normal cursor-default',
                        // Today — always has a ring so it's visible inside the cell, not overlapping neighbors
                        'data-[today]:ring-2 data-[today]:ring-inset data-[today]:ring-blue-500',
                        // Highlighted (hover preview range)
                        'data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground',
                        'data-[highlighted-start]:rounded-l-md data-[highlighted-end]:rounded-r-md',
                        // Selected range fill
                        'data-[selected]:bg-accent data-[selected]:text-accent-foreground',
                        // Range endpoints — important to win over ghost hover + data-[selected]
                        'data-[selection-start]:bg-primary! data-[selection-start]:text-primary-foreground! data-[selection-start]:rounded-l-md',
                        'data-[selection-end]:bg-primary! data-[selection-end]:text-primary-foreground! data-[selection-end]:rounded-r-md',
                        // Disabled / outside
                        'data-[disabled]:text-muted-foreground data-[disabled]:opacity-50',
                        'data-[outside-view]:text-muted-foreground data-[outside-view]:opacity-30',
                      )
                    "
                  />
                  <!-- Dot indicator for marked days — inverts color on range endpoints -->
                  <span
                    v-if="isMarked(weekDate) && weekDate.month === month.value.month"
                    :class="
                      cn(
                        'absolute bottom-1 left-1/2 -translate-x-1/2 size-1 rounded-full pointer-events-none',
                        isEndpoint(weekDate) ? 'bg-primary-foreground' : 'bg-primary',
                      )
                    "
                  />
                </RangeCalendarCell>
              </RangeCalendarGridRow>
            </RangeCalendarGridBody>
          </RangeCalendarGrid>
        </div>

        <!-- Quick action (only when a range is selected) -->
        <div v-if="hasValue" class="border-t mt-3 pt-3 flex justify-center">
          <Button variant="ghost" size="sm" @click="clearSelection">
            <CalendarX2 class="h-4 w-4" />
            {{ resetLabel ?? t('duties.events.filters.resetToToday') }}
          </Button>
        </div>
      </RangeCalendarRoot>
    </PopoverContent>
  </Popover>
</template>
