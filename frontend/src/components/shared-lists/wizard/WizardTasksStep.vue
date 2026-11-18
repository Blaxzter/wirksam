<script setup lang="ts">
/**
 * The wizard's first step: which tasks, on which days, and what that adds up
 * to. The parent holds the selection; this step only shows it and reports
 * changes.
 */
import { computed } from 'vue'

import { I18nT, useI18n } from 'vue-i18n'

import { useSharedListFormat } from '@/composables/useSharedListFormat'

import { Button } from '@/components/ui/button'

import WizardDayCards from '@/components/shared-lists/wizard/WizardDayCards.vue'
import WizardTaskPicker from '@/components/shared-lists/wizard/WizardTaskPicker.vue'

import type { SharedListCandidate } from '@/client/types.gen'
import { type PickedTask, type WizardShift, onlyDays } from '@/lib/shared-list-selection'

const props = defineProps<{
  eventId: string
  picked: readonly PickedTask[]
  shiftsByTask: ReadonlyMap<string, readonly WizardShift[]>
  /** The loaded shifts of the chosen tasks that can be offered. */
  shifts: readonly WizardShift[]
  /** Those of them the list offers. */
  included: readonly WizardShift[]
  shiftsLoading: boolean
  shiftsFailed: boolean
}>()

const excluded = defineModel<Set<string>>('excluded', { required: true })

const emit = defineEmits<{
  pick: [task: SharedListCandidate]
  unpick: [taskId: string]
  retry: []
}>()

const { t } = useI18n()
const { daysText } = useSharedListFormat()

const offeredTaskIds = computed(() =>
  props.picked.filter((task) => !task.unavailable).map((task) => task.id),
)

const freePlaces = computed(() => props.included.reduce((sum, s) => sum + s.free, 0))

const only = computed(() => onlyDays(props.shifts, offeredTaskIds.value, excluded.value))
</script>

<template>
  <div class="grid gap-6">
    <fieldset class="grid gap-3">
      <legend class="mb-3 text-sm font-semibold">
        {{ t('sharedListWizard.picker.legend') }}
      </legend>
      <WizardTaskPicker
        v-model:excluded="excluded"
        :event-id="eventId"
        :picked="picked"
        :shifts-by-task="shiftsByTask"
        @pick="(task) => emit('pick', task)"
        @unpick="(taskId) => emit('unpick', taskId)"
      />
    </fieldset>

    <fieldset class="grid gap-3" data-testid="wizard-days">
      <legend class="mb-3 text-sm font-semibold">
        {{ t('sharedListWizard.days.legend') }}
      </legend>
      <p v-if="offeredTaskIds.length === 0" class="text-sm text-muted-foreground">
        {{ t('sharedListWizard.days.pickTaskFirst') }}
      </p>
      <template v-else>
        <p v-if="shiftsFailed" class="flex flex-wrap items-center gap-2 text-sm text-destructive">
          {{ t('sharedListWizard.blockers.loadFailed') }}
          <Button type="button" variant="outline" size="sm" @click="emit('retry')">
            {{ t('sharedListWizard.actions.retry') }}
          </Button>
        </p>
        <WizardDayCards v-model:excluded="excluded" :shifts="shifts" :task-ids="offeredTaskIds" />
        <p v-if="shiftsLoading" class="text-sm text-muted-foreground" role="status">
          {{ t('common.states.loading') }}
        </p>
        <p class="text-xs text-muted-foreground">{{ t('sharedListWizard.days.hint') }}</p>
        <p class="text-xs text-muted-foreground">{{ t('sharedListWizard.days.laterShifts') }}</p>
      </template>
    </fieldset>

    <div
      v-if="included.length"
      class="grid gap-1 rounded-lg bg-muted px-3 py-2.5 text-sm"
      data-testid="wizard-summary"
    >
      <I18nT keypath="sharedListWizard.summary.text" tag="p" scope="global">
        <template #shifts>
          <strong>
            {{ t('sharedListWizard.summary.shifts', { count: included.length }, included.length) }}
          </strong>
        </template>
        <template #places>
          <strong>
            {{ t('sharedListWizard.summary.places', { count: freePlaces }, freePlaces) }}
          </strong>
        </template>
      </I18nT>
      <p v-if="only">{{ t('sharedListWizard.summary.onlyDays', { days: daysText(only) }) }}</p>
    </div>
  </div>
</template>
