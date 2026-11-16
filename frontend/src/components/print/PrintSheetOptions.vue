<script setup lang="ts">
/**
 * The display options of a printed sheet, in the floating toolbar: columns,
 * the repeated header, the map, names, lines for paper and which days.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Checkbox } from '@/components/ui/checkbox'

const props = defineProps<{
  /** Every day on the sheets, in order. */
  dates: readonly string[]
  /** A sheet has a map to show or leave out. */
  hasMap: boolean
  /** A shared list's sheet: its names are of people signed up, its lines for paper a choice. */
  listed: boolean
  bookingsLoading: boolean
}>()

const showTitle = defineModel<boolean>('showTitle', { required: true })
const showLocation = defineModel<boolean>('showLocation', { required: true })
const repeatHeader = defineModel<boolean>('repeatHeader', { required: true })
const showMap = defineModel<boolean>('showMap', { required: true })
const paperLines = defineModel<boolean>('paperLines', { required: true })
const includeNames = defineModel<boolean>('includeNames', { required: true })
const selectedDates = defineModel<Set<string>>('selectedDates', { required: true })

const { t } = useI18n()
const { formatDateLabel } = useFormatters()

const allSelected = computed(() => selectedDates.value.size === props.dates.length)

function toggleAll() {
  selectedDates.value = allSelected.value ? new Set() : new Set(props.dates)
}

function toggleDate(date: string, checked: boolean | 'indeterminate') {
  const next = new Set(selectedDates.value)
  if (checked === true) next.add(date)
  else next.delete(date)
  selectedDates.value = next
}
</script>

<template>
  <label class="flex items-center gap-2 cursor-pointer">
    <Checkbox v-model="showTitle" />
    <span class="text-sm">{{ t('print.toolbar.showTitle') }}</span>
  </label>
  <label class="flex items-center gap-2 cursor-pointer">
    <Checkbox v-model="showLocation" />
    <span class="text-sm">{{ t('print.toolbar.showLocation') }}</span>
  </label>
  <label class="flex items-center gap-2 cursor-pointer">
    <Checkbox v-model="repeatHeader" />
    <span class="text-sm">{{ t('print.toolbar.repeatHeader') }}</span>
  </label>
  <label v-if="hasMap" class="flex items-center gap-2 cursor-pointer">
    <Checkbox v-model="showMap" data-testid="print-toggle-map" />
    <span class="text-sm">{{ t('print.toolbar.showMap') }}</span>
  </label>

  <div class="border-t pt-2 mt-1 space-y-2">
    <label v-if="listed" class="flex items-center gap-2 cursor-pointer">
      <Checkbox v-model="paperLines" data-testid="print-toggle-paper-lines" />
      <span class="text-sm">{{ t('print.toolbar.paperLines') }}</span>
    </label>
    <label class="flex items-center gap-2 cursor-pointer">
      <Checkbox
        :model-value="includeNames"
        data-testid="print-toggle-names"
        @update:model-value="(value: boolean | 'indeterminate') => (includeNames = value === true)"
      />
      <span class="text-sm">
        {{ listed ? t('print.toolbar.signedUpNames') : t('print.toolbar.includeNames') }}
      </span>
    </label>
    <p v-if="bookingsLoading" class="text-xs text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>
  </div>

  <div v-if="dates.length > 1" class="border-t pt-2 mt-1 space-y-1">
    <span class="text-xs font-medium text-muted-foreground">
      {{ t('print.toolbar.filterDates') }}
    </span>
    <label class="flex items-center gap-2 cursor-pointer">
      <Checkbox
        :model-value="allSelected ? true : selectedDates.size === 0 ? false : 'indeterminate'"
        @update:model-value="toggleAll"
      />
      <span class="text-xs">{{ t('print.optionsDialog.selectAll') }}</span>
    </label>
    <label v-for="date in dates" :key="date" class="flex items-center gap-2 cursor-pointer">
      <Checkbox
        :model-value="selectedDates.has(date)"
        @update:model-value="(value: boolean | 'indeterminate') => toggleDate(date, value)"
      />
      <span class="text-xs">
        {{ formatDateLabel(date, { weekday: 'short', month: 'short', day: 'numeric' }) }}
      </span>
    </label>
  </div>
</template>
