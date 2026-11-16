<script setup lang="ts" generic="K extends string">
/**
 * What a phone shows in place of sortable column headers: the column to sort
 * by, and a button that turns the order round. A new column starts in its own
 * direction, as a header click would.
 */
import { computed, useId } from 'vue'

import { ArrowDownWideNarrow, ArrowUpNarrowWide } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import { useI18n } from 'vue-i18n'

import type { SortDir } from '@/composables/useTableQuery'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const props = defineProps<{
  options: readonly { value: K; label: string }[]
  sort: K
  dir: SortDir
}>()

const emit = defineEmits<{ sort: [key: K, dir?: SortDir] }>()

const { t } = useI18n()
const id = useId()

const key = computed<AcceptableValue>({
  get: () => props.sort,
  set: (value) => {
    const option = props.options.find((o) => o.value === value)
    if (option) emit('sort', option.value)
  },
})
</script>

<template>
  <div class="flex min-w-0 items-center gap-2" data-testid="sort-select">
    <label :for="id" class="shrink-0 text-sm text-muted-foreground">
      {{ t('common.sort.label') }}
    </label>
    <Select v-model="key">
      <SelectTrigger :id="id" class="h-11 min-w-0 flex-1" data-testid="sort-select-key">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="option in props.options" :key="option.value" :value="option.value">
          {{ option.label }}
        </SelectItem>
      </SelectContent>
    </Select>
    <Button
      variant="outline"
      size="icon"
      class="size-11 shrink-0"
      :aria-label="t('common.sort.descending')"
      :aria-pressed="props.dir === 'desc'"
      data-testid="sort-select-dir"
      @click="emit('sort', props.sort, props.dir === 'asc' ? 'desc' : 'asc')"
    >
      <ArrowDownWideNarrow v-if="props.dir === 'desc'" aria-hidden="true" />
      <ArrowUpNarrowWide v-else aria-hidden="true" />
    </Button>
  </div>
</template>
