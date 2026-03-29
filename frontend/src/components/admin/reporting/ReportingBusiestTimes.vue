<script setup lang="ts">
import { computed, ref } from 'vue'

import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import type { BookingsByHour } from '@/client/types.gen'

const props = defineProps<{
  hours: BookingsByHour[]
}>()

const { t, locale } = useI18n()

function formatHour(hour: number): string {
  const d = new Date(2000, 0, 1, hour)
  return d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
}

const hourFrom = ref('6')
const hourTo = ref('23')

const allHours = Array.from({ length: 24 }, (_, i) => ({
  value: String(i),
  label: `${i.toString().padStart(2, '0')}:00`,
}))

const bars = computed(() => {
  const from = Number(hourFrom.value)
  const to = Number(hourTo.value)
  const lookup = new Map(props.hours.map((h) => [h.hour, h.booking_count]))
  const result: { hour: number; count: number }[] = []
  for (let h = from; h <= to; h++) {
    result.push({ hour: h, count: lookup.get(h) ?? 0 })
  }
  return result
})

const maxCount = computed(() => Math.max(...bars.value.map((b) => b.count), 1))

function barSize(count: number): string {
  if (count === 0) return '2px'
  const pct = Math.max((count / maxCount.value) * 100, 8)
  return `${pct}%`
}
</script>

<template>
  <Card class="flex flex-col">
    <CardHeader>
      <div class="flex items-start justify-between gap-4">
        <div>
          <CardTitle>{{ t('admin.reporting.busiestTimes.title') }}</CardTitle>
          <CardDescription>{{ t('admin.reporting.busiestTimes.description') }}</CardDescription>
        </div>
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
          <Select v-model="hourFrom">
            <SelectTrigger class="h-7 w-[80px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="h in allHours.filter((h) => Number(h.value) < Number(hourTo))"
                :key="h.value"
                :value="h.value"
              >
                {{ h.label }}
              </SelectItem>
            </SelectContent>
          </Select>
          <span>–</span>
          <Select v-model="hourTo">
            <SelectTrigger class="h-7 w-[80px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="h in allHours.filter((h) => Number(h.value) > Number(hourFrom))"
                :key="h.value"
                :value="h.value"
              >
                {{ h.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </CardHeader>
    <CardContent class="flex-1 flex flex-col justify-between">
      <div class="flex flex-col justify-between h-full gap-0.5">
        <div
          v-for="bar in bars"
          :key="bar.hour"
          class="flex items-center gap-2 group flex-1"
        >
          <span class="text-[11px] text-muted-foreground tabular-nums w-12 text-right shrink-0">
            {{ formatHour(bar.hour) }}
          </span>
          <div class="relative flex-1 h-5">
            <div
              class="absolute inset-y-0 left-0 rounded-r-sm transition-all"
              :class="bar.count > 0 ? 'bg-primary' : 'bg-muted/50'"
              :style="{ width: barSize(bar.count) }"
            />
          </div>
          <span
            class="text-[11px] tabular-nums w-6 text-right shrink-0 transition-opacity"
            :class="bar.count > 0 ? 'text-foreground font-medium' : 'text-muted-foreground/50'"
          >
            {{ bar.count }}
          </span>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
