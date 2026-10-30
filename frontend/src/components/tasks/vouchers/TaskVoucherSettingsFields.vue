<script setup lang="ts">
import { watch } from 'vue'

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
 * A task's voucher settings: how many each shift earns, whether the task is a
 * place that takes them, and whether that place is the volunteer desk where
 * staff may also redeem without a code. Used by the task page's dialog and by
 * the create form; neither sends anything until it saves.
 */
const props = defineProps<{
  /** Prefix for the field ids, so two forms on one page never share one. */
  idPrefix: string
}>()

const perShift = defineModel<number>('vouchersPerShift', { required: true })
const isPoint = defineModel<boolean>('isPoint', { required: true })
const isDesk = defineModel<boolean>('isDesk', { required: true })

const { t } = useI18n()

/** The server's limit per task. */
const MAX_PER_SHIFT = 50

// A desk is a kind of point; without the point it means nothing.
watch(isPoint, (on) => {
  if (!on) isDesk.value = false
})

const id = (name: string) => `${props.idPrefix}-${name}`
</script>

<template>
  <div class="space-y-4">
    <NumberField
      :id="id('per-shift')"
      v-model="perShift"
      :min="0"
      :max="MAX_PER_SHIFT"
      class="max-w-48"
      data-testid="voucher-per-shift"
    >
      <Label :for="id('per-shift')">{{ t('vouchers.settings.perShift') }}</Label>
      <NumberFieldContent>
        <NumberFieldDecrement :aria-label="t('common.actions.decrease')" />
        <NumberFieldInput />
        <NumberFieldIncrement
          :aria-label="t('common.actions.increase')"
          data-testid="btn-voucher-per-shift-increase"
        />
      </NumberFieldContent>
    </NumberField>
    <p class="-mt-2 text-xs text-muted-foreground">{{ t('vouchers.settings.perShiftHint') }}</p>

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

    <div v-if="isPoint" class="flex items-start justify-between gap-4 rounded-md border p-3">
      <div class="space-y-1">
        <Label :for="id('is-desk')">{{ t('vouchers.settings.isDesk') }}</Label>
        <p class="text-xs text-muted-foreground">{{ t('vouchers.settings.isDeskHint') }}</p>
      </div>
      <Switch
        :id="id('is-desk')"
        :model-value="isDesk"
        data-testid="voucher-is-desk"
        @update:model-value="(v: boolean) => (isDesk = v)"
      />
    </div>

    <p class="text-xs text-muted-foreground">{{ t('vouchers.settings.retroHint') }}</p>
  </div>
</template>
