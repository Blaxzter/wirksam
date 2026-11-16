<script setup lang="ts">
/**
 * "Leave out single shifts" under one chosen task: every shift of it that has
 * not started, by day, each with its own checkbox. It lists the days that are
 * unticked too, so one shift can be taken back in on a day that is otherwise
 * left out (that day then reads as mixed).
 */
import { computed, ref, useId } from 'vue'

import { useI18n } from 'vue-i18n'

import { useSharedListFormat } from '@/composables/useSharedListFormat'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

import { type WizardShift, setShiftIncluded, shiftsByDay } from '@/lib/shared-list-selection'

const props = defineProps<{
  taskId: string
  taskName: string
  /** The task's shifts that have not started. */
  shifts: readonly WizardShift[]
}>()

const excluded = defineModel<Set<string>>('excluded', { required: true })

const { t } = useI18n()
const { shortDay, timeRange } = useSharedListFormat()

const open = ref(false)
const listId = useId()

const days = computed(() => [...shiftsByDay(props.shifts, [props.taskId])])

function setIncluded(shiftId: string, value: boolean | 'indeterminate') {
  excluded.value = setShiftIncluded(excluded.value, shiftId, value === true)
}
</script>

<template>
  <div class="grid gap-2">
    <Button
      type="button"
      variant="link"
      size="sm"
      class="h-auto justify-self-start px-0 py-1"
      :aria-expanded="open"
      :aria-controls="listId"
      :data-testid="`wizard-task-shifts-toggle-${taskId}`"
      @click="open = !open"
    >
      {{ open ? t('sharedListWizard.shifts.hide') : t('sharedListWizard.shifts.show') }}
    </Button>
    <div
      v-if="open"
      :id="listId"
      role="group"
      :aria-label="t('sharedListWizard.shifts.group', { task: taskName })"
      class="grid gap-3 border-t border-dashed pt-2"
    >
      <div v-for="[date, dayShifts] in days" :key="date" class="grid gap-1">
        <p :id="`${listId}-${date}`" class="text-xs font-semibold text-muted-foreground">
          {{ shortDay(date) }}
        </p>
        <ul class="grid gap-x-4 sm:grid-cols-2" :aria-labelledby="`${listId}-${date}`">
          <li v-for="shift in dayShifts" :key="shift.id">
            <label
              :for="`wizard-shift-${shift.id}`"
              class="flex cursor-pointer items-center gap-2 py-1.5 text-sm tabular-nums"
            >
              <Checkbox
                :id="`wizard-shift-${shift.id}`"
                :model-value="!excluded.has(shift.id)"
                :data-testid="`wizard-shift-check-${shift.id}`"
                @update:model-value="(value) => setIncluded(shift.id, value)"
              />
              <span>
                {{
                  timeRange(shift.start_time, shift.end_time) || t('sharedListWizard.shifts.allDay')
                }}
              </span>
              <span class="text-muted-foreground">
                ·
                {{
                  shift.free > 0
                    ? t('sharedListWizard.shifts.free', { count: shift.free })
                    : t('sharedListWizard.shifts.full')
                }}
              </span>
            </label>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
