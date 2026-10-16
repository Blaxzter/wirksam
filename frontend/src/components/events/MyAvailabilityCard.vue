<script setup lang="ts">
import { computed } from 'vue'

import { Calendar, CircleDot, Clock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import AvailabilityPaintGrid from '@/components/events/AvailabilityPaintGrid.vue'
import DailyWindowPicker from '@/components/events/DailyWindowPicker.vue'

type AvailabilityType = 'fully_available' | 'specific_dates' | 'time_range'

const props = defineProps<{
  days: Date[]
  hours: number[]
  mode: AvailabilityType
  avail: Set<string>
  dailyFrom: number
  dailyTo: number
  dailyExcluded: Set<number>
}>()

const emit = defineEmits<{
  'update:mode': [value: AvailabilityType]
  'update:avail': [value: Set<string>]
  'update:dailyFrom': [value: number]
  'update:dailyTo': [value: number]
  'update:dailyExcluded': [value: Set<number>]
}>()

const { t } = useI18n()

const totalHours = computed(() => {
  if (props.mode === 'fully_available') return props.hours.length * props.days.length
  if (props.mode === 'time_range') {
    const enabled = props.days.length - props.dailyExcluded.size
    return Math.max(0, props.dailyTo - props.dailyFrom) * enabled
  }
  return props.avail.size
})

const totalDays = computed(() => {
  if (props.mode === 'fully_available') return props.days.length
  if (props.mode === 'time_range') return props.days.length - props.dailyExcluded.size
  return new Set([...props.avail].map((k) => k.split('-')[0])).size
})

const modes: { key: AvailabilityType; title: string; sub: string; icon: unknown }[] = [
  {
    key: 'fully_available',
    title: t('duties.availability.modeFull'),
    sub: t('duties.availability.modeFullSub'),
    icon: CircleDot,
  },
  {
    key: 'time_range',
    title: t('duties.availability.modeTimeRange'),
    sub: t('duties.availability.modeTimeRangeSub'),
    icon: Clock,
  },
  {
    key: 'specific_dates',
    title: t('duties.availability.modeSpecific'),
    sub: t('duties.availability.modeSpecificSub'),
    icon: Calendar,
  },
]

const shortModes: { key: AvailabilityType; label: string }[] = [
  { key: 'fully_available', label: t('duties.availability.modeShort.full') },
  { key: 'time_range', label: t('duties.availability.modeShort.time_range') },
  { key: 'specific_dates', label: t('duties.availability.modeShort.specific') },
]

const daysWord = computed(() => t('duties.availability.days'))
</script>

<template>
  <div class="space-y-4">
    <!-- Mode picker (desktop): cards with summary box -->
    <div class="hidden gap-5 sm:flex" data-testid="availability-mode-picker">
      <div class="flex-1">
        <div
          class="text-muted-foreground mb-2 text-[11px] font-semibold uppercase tracking-wider"
        >
          {{ t('duties.availability.typeLabel') }}
        </div>
        <div class="flex gap-2">
          <button
            v-for="m in modes"
            :key="m.key"
            type="button"
            :data-testid="`availability-type-${m.key}`"
            class="flex flex-1 items-center gap-3 rounded-lg border p-3 text-left transition-colors"
            :class="
              mode === m.key
                ? 'border-primary bg-primary/10'
                : 'border-border bg-background hover:border-primary/40'
            "
            @click="emit('update:mode', m.key)"
          >
            <div
              class="flex size-9 shrink-0 items-center justify-center rounded-md border"
              :class="
                mode === m.key
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'bg-card text-muted-foreground'
              "
            >
              <component :is="m.icon" class="size-5" />
            </div>
            <div class="min-w-0">
              <div
                class="text-[13px] font-semibold leading-tight"
                :class="mode === m.key ? 'text-primary' : 'text-foreground'"
              >
                {{ m.title }}
              </div>
              <div class="text-muted-foreground mt-0.5 text-[11px]">{{ m.sub }}</div>
            </div>
          </button>
        </div>
      </div>

      <!-- Summary chip -->
      <div class="bg-primary/10 w-[220px] shrink-0 rounded-lg p-3.5">
        <div class="text-primary text-[10px] font-semibold uppercase tracking-wider">
          {{ t('duties.availability.yourSummary') }}
        </div>
        <div class="mt-1 flex items-baseline gap-1.5">
          <span class="text-primary text-2xl font-bold leading-none tracking-tight">
            {{ totalHours }}
          </span>
          <span class="text-primary text-xs font-medium">
            {{ t('duties.availability.hours') }}
          </span>
          <span class="text-primary opacity-50">·</span>
          <span class="text-primary text-lg font-bold tracking-tight">{{ totalDays }}</span>
          <span class="text-primary text-xs font-medium">
            {{ daysWord }}
          </span>
        </div>
        <div class="text-primary mt-1 text-[11px]">
          {{ t('duties.availability.summaryHint') }}
        </div>
      </div>
    </div>

    <!-- Mobile mode picker: 3 segmented buttons -->
    <div class="sm:hidden">
      <div class="mb-3 flex gap-1.5" data-testid="availability-mode-picker">
        <button
          v-for="m in shortModes"
          :key="m.key"
          type="button"
          :data-testid="`availability-type-${m.key}`"
          class="flex-1 rounded-md border px-2 py-2 text-center text-[12px] font-semibold transition-colors"
          :class="
            mode === m.key
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border bg-card text-foreground'
          "
          @click="emit('update:mode', m.key)"
        >
          {{ m.label }}
        </button>
      </div>

      <div class="bg-primary/10 mb-3 flex items-center gap-3 rounded-lg p-2.5">
        <div class="min-w-0 flex-1">
          <div class="text-primary text-[11px] font-semibold uppercase tracking-wider">
            {{ t('duties.availability.summary') }}
          </div>
          <div class="text-primary text-lg font-bold tracking-tight leading-tight">
            {{ totalHours }}h · {{ totalDays }} {{ daysWord }}
          </div>
        </div>
      </div>
    </div>

    <!-- Mode-specific content -->
    <div v-if="mode === 'fully_available'" data-testid="availability-editor">
      <div
        class="bg-primary/10 border-primary rounded-lg border-[1.5px] border-dashed p-6 text-center"
      >
        <div class="text-primary text-lg font-semibold tracking-tight">
          {{ t('duties.availability.fullyAvailableDays', { count: days.length }) }}
        </div>
        <div class="text-primary mt-1 text-[12px]">
          {{ t('duties.availability.fullyAvailableHint') }}
        </div>
      </div>
    </div>

    <div v-else-if="mode === 'time_range'" data-testid="availability-editor">
      <DailyWindowPicker
        :days="days"
        :from="dailyFrom"
        :to="dailyTo"
        :excluded-days="dailyExcluded"
        @update:from="(v) => emit('update:dailyFrom', v)"
        @update:to="(v) => emit('update:dailyTo', v)"
        @update:excluded-days="(v) => emit('update:dailyExcluded', v)"
      />
    </div>

    <div v-else data-testid="availability-editor">
      <AvailabilityPaintGrid
        :days="days"
        :hours="hours"
        :model-value="avail"
        @update:model-value="(v) => emit('update:avail', v)"
      />
    </div>
  </div>
</template>
