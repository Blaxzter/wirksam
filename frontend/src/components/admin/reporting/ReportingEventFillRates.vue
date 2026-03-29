<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

import type { EventFillRate } from '@/client/types.gen'

defineProps<{
  events: EventFillRate[]
}>()

const { t } = useI18n()
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ t('admin.reporting.eventFillRates.title') }}</CardTitle>
      <CardDescription>{{ t('admin.reporting.eventFillRates.description') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('admin.reporting.eventFillRates.event') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.eventFillRates.capacity') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.eventFillRates.booked') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.eventFillRates.fillRate') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="event in events" :key="event.event_id">
            <TableCell class="font-medium">{{ event.event_name }}</TableCell>
            <TableCell class="text-right tabular-nums">{{ event.total_capacity }}</TableCell>
            <TableCell class="text-right tabular-nums">{{ event.confirmed_bookings }}</TableCell>
            <TableCell class="text-right">
              <div class="flex items-center justify-end gap-2">
                <div class="w-16 h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="
                      event.fill_rate >= 80
                        ? 'bg-green-500'
                        : event.fill_rate >= 50
                          ? 'bg-yellow-500'
                          : 'bg-red-500'
                    "
                    :style="{ width: `${Math.min(event.fill_rate, 100)}%` }"
                  />
                </div>
                <span class="tabular-nums text-sm font-medium w-12 text-right">
                  {{ event.fill_rate }}%
                </span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </CardContent>
  </Card>
</template>
