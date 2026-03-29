<script setup lang="ts">
import { BarChart3, Calendar, TrendingUp, Users } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { ReportingOverviewStats } from '@/client/types.gen'

defineProps<{
  overview: ReportingOverviewStats
}>()

const { t } = useI18n()
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm font-medium">
            {{ t('admin.reporting.overview.totalBookings') }}
          </CardTitle>
          <BarChart3 class="size-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ overview.total_bookings }}</div>
        <p class="text-xs text-muted-foreground">
          {{ overview.confirmed_bookings }}
          {{ t('admin.reporting.overview.confirmedBookings') }} ·
          {{ overview.cancelled_bookings }}
          {{ t('admin.reporting.overview.cancelledBookings') }}
        </p>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm font-medium">
            {{ t('admin.reporting.overview.fillRate') }}
          </CardTitle>
          <TrendingUp class="size-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ overview.fill_rate }}%</div>
        <p class="text-xs text-muted-foreground">
          {{ overview.confirmed_bookings }} / {{ overview.total_slot_capacity }}
          {{ t('admin.reporting.overview.totalCapacity') }}
        </p>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm font-medium">
            {{ t('admin.reporting.overview.totalEvents') }}
          </CardTitle>
          <Calendar class="size-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ overview.total_events }}</div>
        <p class="text-xs text-muted-foreground">
          {{ overview.total_slots }} {{ t('admin.reporting.overview.totalSlots') }} ·
          {{ overview.filled_slots }} {{ t('admin.reporting.overview.filledSlots') }}
        </p>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm font-medium">
            {{ t('admin.reporting.overview.activeVolunteers') }}
          </CardTitle>
          <Users class="size-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ overview.active_volunteers }}</div>
        <p class="text-xs text-muted-foreground">
          {{ overview.total_volunteers }}
          {{ t('admin.reporting.overview.totalVolunteers') }} ·
          {{ overview.cancellation_rate }}%
          {{ t('admin.reporting.overview.cancellationRate') }}
        </p>
      </CardContent>
    </Card>
  </div>
</template>
