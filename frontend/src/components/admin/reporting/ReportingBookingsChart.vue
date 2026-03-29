<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { VisAxis, VisLine, VisXYContainer } from '@unovis/vue'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import type { BookingsTrendPoint } from '@/client/types.gen'

const props = defineProps<{
  trend: BookingsTrendPoint[]
}>()

const { t, locale } = useI18n()

type Granularity = 'day' | 'month'
type Datum = { x: number; confirmed: number; cancelled: number; label: string }

const granularity = ref<Granularity>('day')

function formatDay(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

function formatMonth(key: string): string {
  const [year, m] = key.split('-')
  const d = new Date(Number(year), Number(m) - 1)
  return d.toLocaleDateString(locale.value, { year: 'numeric', month: 'short' })
}

function toDayData(input: BookingsTrendPoint[]): Datum[] {
  return input.map((p, i) => ({
    x: i,
    confirmed: p.confirmed,
    cancelled: p.cancelled,
    label: formatDay(p.date),
  }))
}

function toMonthData(input: BookingsTrendPoint[]): Datum[] {
  const grouped = new Map<string, { confirmed: number; cancelled: number }>()
  for (const p of input) {
    const key = p.date.slice(0, 7) // "YYYY-MM"
    const entry = grouped.get(key) ?? { confirmed: 0, cancelled: 0 }
    entry.confirmed += p.confirmed
    entry.cancelled += p.cancelled
    grouped.set(key, entry)
  }
  return Array.from(grouped.entries()).map(([key, val], i) => ({
    x: i,
    confirmed: val.confirmed,
    cancelled: val.cancelled,
    label: formatMonth(key),
  }))
}

const data = ref<Datum[]>([])

function syncData() {
  data.value =
    granularity.value === 'day' ? toDayData(props.trend) : toMonthData(props.trend)
}

syncData()
watch([() => props.trend, granularity], syncData)

// Auto-select month when there are many day points
const autoGranularity = computed(() => {
  if (props.trend.length > 60) return 'month'
  return null
})
watch(autoGranularity, (val) => {
  if (val) granularity.value = val
}, { immediate: true })

const xFn = (d: Datum) => d.x
const yConfirmed = (d: Datum) => d.confirmed
const yCancelled = (d: Datum) => d.cancelled
const tickFormat = (i: number) => data.value[i]?.label ?? ''
</script>

<template>
  <Card>
    <CardHeader>
      <div class="flex items-start justify-between gap-4">
        <div>
          <CardTitle>{{ t('admin.reporting.bookingsByMonth.title') }}</CardTitle>
          <CardDescription>{{ t('admin.reporting.bookingsByMonth.description') }}</CardDescription>
        </div>
        <div class="flex rounded-md border overflow-hidden shrink-0">
          <Button
            variant="ghost"
            size="sm"
            class="rounded-none h-7 px-3 text-xs"
            :class="granularity === 'day' && 'bg-muted'"
            @click="granularity = 'day'"
          >
            {{ t('admin.reporting.granularity.day') }}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            class="rounded-none border-l h-7 px-3 text-xs"
            :class="granularity === 'month' && 'bg-muted'"
            @click="granularity = 'month'"
          >
            {{ t('admin.reporting.granularity.month') }}
          </Button>
        </div>
      </div>
    </CardHeader>
    <CardContent class="px-2 sm:p-6">
      <div class="h-[250px] w-full">
        <VisXYContainer
          v-if="data.length > 1"
          :data="data"
          :height="250"
          :duration="0"
        >
          <VisLine
            :x="xFn"
            :y="yConfirmed"
            color="var(--color-primary)"
            :line-width="2"
            :duration="0"
          />
          <VisLine
            :x="xFn"
            :y="yCancelled"
            color="var(--color-destructive)"
            :line-width="2"
            :line-dash-array="[4, 4]"
            :duration="0"
          />
          <VisAxis
            type="x"
            :tick-format="tickFormat"
            :tick-line="false"
            :domain-line="false"
            :grid-line="false"
            :num-ticks="Math.min(data.length, 8)"
          />
          <VisAxis type="y" :tick-line="false" :domain-line="false" :num-ticks="4" />
        </VisXYContainer>
        <div
          v-else-if="data.length === 1"
          class="flex items-center justify-center h-full text-muted-foreground text-sm"
        >
          {{ data[0].label }}: {{ data[0].confirmed }}
          {{ t('admin.reporting.overview.confirmedBookings') }}
          <template v-if="data[0].cancelled > 0">
            · {{ data[0].cancelled }} {{ t('admin.reporting.overview.cancelledBookings') }}
          </template>
        </div>
      </div>
      <div class="flex items-center justify-center gap-4 mt-2 text-xs text-muted-foreground">
        <span class="flex items-center gap-1.5">
          <span class="size-2.5 rounded-full bg-primary" />
          {{ t('admin.reporting.overview.confirmedBookings') }}
        </span>
        <span class="flex items-center gap-1.5">
          <span class="size-2.5 rounded-full bg-destructive" />
          {{ t('admin.reporting.overview.cancelledBookings') }}
        </span>
      </div>
    </CardContent>
  </Card>
</template>
