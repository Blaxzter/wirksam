<script setup lang="ts">
import { useId } from 'vue'

import { MonitorIcon, SmartphoneIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { DocDevice } from '@/lib/doc-types'

/** Whether a page's screenshots show WirkSam on a computer or on a phone. */
const device = defineModel<DocDevice>({ required: true })

const { t } = useI18n()
// The page shows one beside its contents on a wide screen, and one above the text otherwise.
const labelId = useId()

const OPTIONS = [
  { value: 'desktop', icon: MonitorIcon },
  { value: 'phone', icon: SmartphoneIcon },
] as const
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
    <span :id="labelId" class="text-sm font-semibold">
      {{ t('preauth.docs.device.label') }}
    </span>
    <div
      role="group"
      :aria-labelledby="labelId"
      class="inline-flex rounded-full border bg-card p-1 shadow-sm"
    >
      <button
        v-for="option in OPTIONS"
        :key="option.value"
        type="button"
        :aria-pressed="device === option.value"
        :data-testid="`doc-device-${option.value}`"
        class="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        :class="
          device === option.value
            ? 'bg-(--art)/25 text-foreground ring-1 ring-(--art)'
            : 'text-muted-foreground hover:text-foreground'
        "
        @click="device = option.value"
      >
        <component :is="option.icon" class="size-4" aria-hidden="true" />
        {{ t(`preauth.docs.device.${option.value}`) }}
      </button>
    </div>
  </div>
</template>
