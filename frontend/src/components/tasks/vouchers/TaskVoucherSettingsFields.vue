<script setup lang="ts">
import { Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Label from '@/components/ui/label/Label.vue'
import {
  NumberField,
  NumberFieldContent,
  NumberFieldDecrement,
  NumberFieldIncrement,
  NumberFieldInput,
} from '@/components/ui/number-field'
import Switch from '@/components/ui/switch/Switch.vue'

/**
 * A task's voucher settings: how many each shift earns and whether the task is
 * a place that takes them. Who may also redeem without a code is one rule for
 * the whole event (its settings), so it is not asked here. Used by the task
 * page's dialog and by the create form; neither sends anything until it saves.
 */
const props = defineProps<{
  /** Prefix for the field ids, so two forms on one page never share one. */
  idPrefix: string
  /**
   * The create form's version: its own "Vouchers" group with a heading, and
   * the number on one short line ("Per shift", the field, "0 means none")
   * instead of the dialog's label and full sentence. The dialog's title
   * already says what the fields are about, so it leaves this off.
   */
  compact?: boolean
}>()

const perShift = defineModel<number>('vouchersPerShift', { required: true })
const isPoint = defineModel<boolean>('isPoint', { required: true })

const { t } = useI18n()

/** The server's limit per task. */
const MAX_PER_SHIFT = 50

/**
 * Emptying the field leaves the number field without a number. That means
 * "none" here, so it becomes 0 rather than a value the save would drop.
 */
function setPerShift(value: number | undefined) {
  perShift.value = typeof value === 'number' && Number.isFinite(value) ? value : 0
}

const id = (name: string) => `${props.idPrefix}-${name}`
</script>

<template>
  <component :is="compact ? 'fieldset' : 'div'" class="min-w-0 space-y-4">
    <legend v-if="compact" class="flex items-center gap-2 font-semibold">
      <Ticket class="size-4 text-primary" aria-hidden="true" />
      {{ t('vouchers.settings.title') }}
    </legend>

    <NumberField
      :id="id('per-shift')"
      :model-value="perShift"
      :min="0"
      :max="MAX_PER_SHIFT"
      :class="compact ? 'flex flex-wrap items-center gap-3' : 'max-w-48'"
      data-testid="voucher-per-shift"
      @update:model-value="setPerShift"
    >
      <Label :for="id('per-shift')">
        {{ compact ? t('vouchers.settings.perShiftShort') : t('vouchers.settings.perShift') }}
      </Label>
      <NumberFieldContent :class="compact ? 'w-40' : undefined">
        <NumberFieldDecrement :aria-label="t('common.actions.decrease')" />
        <NumberFieldInput />
        <NumberFieldIncrement
          :aria-label="t('common.actions.increase')"
          data-testid="btn-voucher-per-shift-increase"
        />
      </NumberFieldContent>
      <span v-if="compact" class="text-xs text-muted-foreground">
        {{ t('vouchers.settings.zeroMeansNone') }}
      </span>
    </NumberField>
    <p v-if="!compact" class="-mt-2 text-xs text-muted-foreground">
      {{ t('vouchers.settings.perShiftHint') }}
    </p>

    <div class="flex items-start justify-between gap-4 rounded-md border p-3">
      <div class="space-y-1">
        <Label :for="id('is-point')">{{ t('vouchers.settings.isPoint') }}</Label>
        <p class="text-xs text-muted-foreground">
          {{ isPoint ? t('vouchers.settings.isPointOn') : t('vouchers.settings.isPointOff') }}
        </p>
      </div>
      <Switch
        :id="id('is-point')"
        :model-value="isPoint"
        data-testid="voucher-is-point"
        @update:model-value="(v: boolean) => (isPoint = v)"
      />
    </div>

    <p class="text-xs text-muted-foreground">{{ t('vouchers.settings.rateHint') }}</p>
  </component>
</template>
