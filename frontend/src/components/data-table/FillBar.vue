<script setup lang="ts">
/**
 * How many places are taken, as a bar, with "{free} of {cap} free" under it.
 *
 * The bar fills with the places taken and takes the venue map's staffing
 * colours (`fillLevel`). A screen reader hears it as one progress bar named by
 * `label`, whose value text is that same sentence, so the visible line is
 * hidden from it rather than read twice.
 */
import { computed } from 'vue'

import { I18nT, useI18n } from 'vue-i18n'

import { fillLevel } from '@/lib/shared-lists'
import { STAFFING_CLASSES } from '@/lib/venue-map'

const props = withDefaults(
  defineProps<{
    free: number
    cap: number
    /** The bar's accessible name; "Places" unless given. */
    label?: string
  }>(),
  { label: undefined },
)

const { t } = useI18n()

const cap = computed(() => Math.max(0, props.cap))
const free = computed(() => Math.min(Math.max(0, props.free), cap.value))
const taken = computed(() => cap.value - free.value)
const percent = computed(() => (cap.value > 0 ? Math.round((taken.value / cap.value) * 100) : 0))
const barClass = computed(() => STAFFING_CLASSES[fillLevel(free.value, cap.value)].bg)
</script>

<template>
  <div class="grid min-w-0 gap-1">
    <div
      role="progressbar"
      :aria-label="props.label ?? t('common.fill.label')"
      aria-valuemin="0"
      :aria-valuemax="cap"
      :aria-valuenow="taken"
      :aria-valuetext="t('common.fill.free', { free, cap })"
      class="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      data-testid="fill-bar"
    >
      <div
        class="h-full rounded-full transition-[width] motion-reduce:transition-none"
        :class="barClass"
        :style="{ width: `${percent}%` }"
      />
    </div>
    <I18nT
      keypath="common.fill.free"
      tag="span"
      scope="global"
      class="text-xs text-muted-foreground tabular-nums"
      aria-hidden="true"
    >
      <template #free>
        <span class="font-semibold text-foreground">{{ free }}</span>
      </template>
      <template #cap>{{ cap }}</template>
    </I18nT>
  </div>
</template>
