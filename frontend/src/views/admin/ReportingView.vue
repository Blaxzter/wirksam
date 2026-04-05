<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { BarChart3, Download, EllipsisVertical } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import type { ReportingResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

import ReportingBookingsChart from '@/components/admin/reporting/ReportingBookingsChart.vue'
import ReportingBusiestTimes from '@/components/admin/reporting/ReportingBusiestTimes.vue'
import ReportingCategoryBreakdown from '@/components/admin/reporting/ReportingCategoryBreakdown.vue'
import ReportingEventFillRates from '@/components/admin/reporting/ReportingEventFillRates.vue'
import ReportingOverviewCards from '@/components/admin/reporting/ReportingOverviewCards.vue'
import ReportingTopVolunteers from '@/components/admin/reporting/ReportingTopVolunteers.vue'

const { t } = useI18n()
const { get } = useAuthenticatedClient()
const route = useRoute()
const router = useRouter()

// ---------- Default range: first of current month → today ----------
function monthStartIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}
function nextMonthEndIso(): string {
  const d = new Date()
  // Last day of next month: day 0 of month+2
  const last = new Date(d.getFullYear(), d.getMonth() + 2, 0)
  return last.toISOString().slice(0, 10)
}

// ---------- State ----------
const loading = ref(false)
const exporting = ref(false)
const data = ref<ReportingResponse | null>(null)
const dateFrom = ref<string | null>(null)
const dateTo = ref<string | null>(null)
const markedDays = ref<Set<string>>(new Set())

// ---------- URL sync: read on mount ----------
function readUrlParams() {
  const q = route.query
  const ISO_RE = /^\d{4}-\d{2}-\d{2}$/
  if (q.date_from && ISO_RE.test(String(q.date_from))) {
    dateFrom.value = String(q.date_from)
  } else {
    dateFrom.value = monthStartIso()
  }
  if (q.date_to && ISO_RE.test(String(q.date_to))) {
    dateTo.value = String(q.date_to)
  } else {
    dateTo.value = nextMonthEndIso()
  }
}
readUrlParams()

// ---------- URL sync: write on change ----------
const urlQuery = computed(() => {
  const q: Record<string, string> = {}
  if (dateFrom.value) q.date_from = dateFrom.value
  if (dateTo.value) q.date_to = dateTo.value
  return q
})

watch(urlQuery, (q) => {
  router.replace({ query: q })
})

// ---------- Actions ----------
function buildQueryParams(): string {
  const params = new URLSearchParams()
  if (dateFrom.value) params.set('date_from', dateFrom.value)
  if (dateTo.value) params.set('date_to', dateTo.value)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

async function loadData() {
  loading.value = true
  try {
    const response = await get<{ data: ReportingResponse }>({
      url: `/reporting/overview${buildQueryParams()}`,
    })
    data.value = response.data
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

async function exportCsv() {
  exporting.value = true
  try {
    const response = await get<{ data: string }>({
      url: `/reporting/export${buildQueryParams()}`,
    })
    const blob = new Blob([response.data], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'bookings-report.csv'
    a.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    toastApiError(error)
  } finally {
    exporting.value = false
  }
}

async function handleVisibleMonth(range: { from: string; to: string }) {
  try {
    const res = await get<{ data: string[] }>({
      url: '/events/active-dates',
      query: { date_from: range.from, date_to: range.to },
    })
    markedDays.value = new Set(res.data)
  } catch {
    // Non-critical
  }
}

function handleDateFromUpdate(value: string | null) {
  dateFrom.value = value ?? monthStartIso()
  if ((value && dateTo.value) || (!value && !dateTo.value)) {
    loadData()
  }
}

function handleDateToUpdate(value: string | null) {
  dateTo.value = value ?? nextMonthEndIso()
  if ((dateFrom.value && value) || (!value && !dateFrom.value)) {
    loadData()
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header + actions -->
    <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 data-testid="page-heading" class="text-2xl font-bold tracking-tight">{{ t('admin.reporting.title') }}</h1>
        <p class="text-muted-foreground">{{ t('admin.reporting.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2 mt-2 sm:mt-0">
        <DateRangePicker
          :date-from="dateFrom"
          :date-to="dateTo"
          :marked-days="markedDays"
          :default-label="t('admin.reporting.dateRange')"
          @update:date-from="handleDateFromUpdate"
          @update:date-to="handleDateToUpdate"
          @update:visible-month="handleVisibleMonth"
        />
        <Button
          data-testid="btn-export"
          variant="outline"
          size="sm"
          class="hidden sm:inline-flex"
          :disabled="exporting"
          @click="exportCsv()"
        >
          <Download class="mr-2 size-4" />
          {{ t('admin.reporting.export') }}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm" class="sm:hidden">
              <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem :disabled="exporting" @click="exportCsv()">
              <Download class="mr-2 size-4" />
              {{ t('admin.reporting.export') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12 text-muted-foreground">
      <BarChart3 class="mr-2 size-5 animate-pulse" />
      {{ t('admin.reporting.overview.title') }}...
    </div>

    <!-- Data -->
    <template v-else-if="data">
      <ReportingOverviewCards data-testid="section-overview" :overview="data.overview" />

      <div data-testid="section-charts">
      <ReportingBookingsChart
        v-if="data.bookings_trend?.length > 0"
        :trend="data.bookings_trend"
      />

      <div class="grid gap-4 lg:grid-cols-2">
        <ReportingTopVolunteers
          v-if="data.top_volunteers.length > 0"
          :volunteers="data.top_volunteers"
        />
        <ReportingBusiestTimes
          v-if="data.bookings_by_hour?.length > 0"
          :hours="data.bookings_by_hour"
        />
      </div>

      <ReportingCategoryBreakdown
        v-if="data.category_breakdown.length > 0"
        :categories="data.category_breakdown"
      />

      <ReportingEventFillRates
        v-if="data.event_fill_rates.length > 0"
        :events="data.event_fill_rates"
      />
      </div>

      <!-- No data state -->
      <Card v-if="data.overview.total_bookings === 0 && data.overview.total_events === 0">
        <CardContent class="flex items-center justify-center py-12 text-muted-foreground">
          {{ t('admin.reporting.noData') }}
        </CardContent>
      </Card>
    </template>
  </div>
</template>
