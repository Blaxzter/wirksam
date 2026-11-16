<script setup lang="ts">
/**
 * One card per day the chosen tasks have shifts on, each with a checkbox that
 * is read off the day's shifts: ticked when all are in, mixed when some are,
 * empty when none are. Ticking it takes all of them in or out of the one set
 * of excluded shifts the parent holds, so the cards and the single shifts
 * further up can never disagree.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useSharedListFormat } from '@/composables/useSharedListFormat'

import TriStateCheckbox from '@/components/data-table/TriStateCheckbox.vue'

import {
  type DayState,
  type WizardShift,
  dayState,
  shiftsByDay,
  toggleDay,
} from '@/lib/shared-list-selection'

const props = defineProps<{
  /** The loaded shifts of the chosen tasks. */
  shifts: readonly WizardShift[]
  taskIds: readonly string[]
}>()

const excluded = defineModel<Set<string>>('excluded', { required: true })

const { t } = useI18n()
const { shortDay } = useSharedListFormat()

interface DayCard {
  date: string
  shifts: WizardShift[]
  state: DayState
  included: number
  free: number
}

const cards = computed<DayCard[]>(() =>
  [...shiftsByDay(props.shifts, props.taskIds)].map(([date, shifts]) => {
    const kept = shifts.filter((s) => !excluded.value.has(s.id))
    return {
      date,
      shifts,
      state: dayState(shifts, excluded.value),
      included: kept.length,
      free: kept.reduce((sum, s) => sum + s.free, 0),
    }
  }),
)

function checkboxValue(state: DayState): boolean | 'indeterminate' {
  return state === 'indeterminate' ? 'indeterminate' : state === 'checked'
}

function toggle(card: DayCard) {
  excluded.value = toggleDay(card.shifts, excluded.value)
}
</script>

<template>
  <ul class="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2">
    <li v-for="card in cards" :key="card.date">
      <label
        :for="`wizard-day-${card.date}`"
        class="flex h-full cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors"
        :class="card.state === 'unchecked' ? 'bg-card' : 'border-primary/60 bg-primary/5'"
        :data-testid="`wizard-day-${card.date}`"
        :data-state="card.state"
      >
        <TriStateCheckbox
          :id="`wizard-day-${card.date}`"
          :model-value="checkboxValue(card.state)"
          :data-testid="`wizard-day-check-${card.date}`"
          @update:model-value="toggle(card)"
        />
        <span class="grid min-w-0 leading-snug">
          <span class="text-sm font-semibold">{{ shortDay(card.date) }}</span>
          <span class="text-xs text-muted-foreground">
            {{
              t(
                'sharedListWizard.days.shifts',
                { included: card.included, total: card.shifts.length },
                card.shifts.length,
              )
            }}
            <template v-if="card.included > 0">
              ·
              <span v-if="card.free > 0">
                {{ t('sharedListWizard.days.free', { count: card.free }) }}
              </span>
              <span v-else class="font-semibold text-warning">
                {{ t('sharedListWizard.days.full') }}
              </span>
            </template>
          </span>
        </span>
      </label>
    </li>
  </ul>
</template>
