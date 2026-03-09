<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DateValue } from '@internationalized/date'
import { DateFormatter, getLocalTimeZone } from '@internationalized/date'
import { CalendarIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const model = defineModel<DateValue>()

defineProps<{
  placeholder?: string
  minValue?: DateValue
  maxValue?: DateValue
  highlight?: DateValue
}>()

const { t, locale } = useI18n()

const open = ref(false)

const df = computed(() => new DateFormatter(locale.value, { dateStyle: 'medium' }))

const displayText = computed(() =>
  model.value
    ? df.value.format(model.value.toDate(getLocalTimeZone()))
    : undefined,
)

function onSelect(value: DateValue | undefined) {
  model.value = value
  open.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        :class="
          cn(
            'w-full min-w-0 justify-start text-left font-normal',
            !model && 'text-muted-foreground',
          )
        "
      >
        <CalendarIcon class="mr-2 h-4 w-4 shrink-0" />
        <span class="truncate">{{ displayText ?? placeholder ?? t('duties.events.pickDate') }}</span>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-auto p-0">
      <Calendar
        :model-value="model"
        layout="month-and-year"
        :locale="locale"
        :min-value="minValue"
        :max-value="maxValue"
        :highlight="highlight"
        @update:model-value="onSelect"
      />
    </PopoverContent>
  </Popover>
</template>
