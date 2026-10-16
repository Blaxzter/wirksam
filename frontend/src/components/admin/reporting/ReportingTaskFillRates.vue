<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import type { TaskFillRate } from '@/client/types.gen'

defineProps<{
  tasks: TaskFillRate[]
}>()

const { t } = useI18n()

function fillClass(rate: number): string {
  if (rate >= 80) return 'bg-green-500'
  if (rate >= 50) return 'bg-yellow-500'
  return 'bg-red-500'
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ t('admin.reporting.eventFillRates.title') }}</CardTitle>
      <CardDescription>{{ t('admin.reporting.eventFillRates.description') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <!-- Phones: one stacked row per task; four columns would scroll sideways. -->
      <ul class="divide-y sm:hidden">
        <li v-for="task in tasks" :key="task.task_id" class="space-y-1.5 py-3 first:pt-0 last:pb-0">
          <div class="flex items-baseline justify-between gap-3">
            <span class="min-w-0 truncate font-medium">{{ task.task_name }}</span>
            <span class="shrink-0 text-sm font-medium tabular-nums">{{ task.fill_rate }}%</span>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-muted">
            <div
              class="h-full rounded-full"
              :class="fillClass(task.fill_rate)"
              :style="{ width: `${Math.min(task.fill_rate, 100)}%` }"
            />
          </div>
          <p class="text-xs text-muted-foreground tabular-nums">
            {{ t('admin.reporting.eventFillRates.booked') }} {{ task.confirmed_bookings }} ·
            {{ t('admin.reporting.eventFillRates.capacity') }} {{ task.total_capacity }}
          </p>
        </li>
      </ul>
      <Table class="max-sm:hidden">
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('admin.reporting.eventFillRates.task') }}</TableHead>
            <TableHead class="text-right">{{
              t('admin.reporting.eventFillRates.capacity')
            }}</TableHead>
            <TableHead class="text-right">{{
              t('admin.reporting.eventFillRates.booked')
            }}</TableHead>
            <TableHead class="text-right">{{
              t('admin.reporting.eventFillRates.fillRate')
            }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="task in tasks" :key="task.task_id">
            <TableCell class="font-medium">{{ task.task_name }}</TableCell>
            <TableCell class="text-right tabular-nums">{{ task.total_capacity }}</TableCell>
            <TableCell class="text-right tabular-nums">{{ task.confirmed_bookings }}</TableCell>
            <TableCell class="text-right">
              <div class="flex items-center justify-end gap-2">
                <div class="w-16 h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="fillClass(task.fill_rate)"
                    :style="{ width: `${Math.min(task.fill_rate, 100)}%` }"
                  />
                </div>
                <span class="tabular-nums text-sm font-medium w-12 text-right">
                  {{ task.fill_rate }}%
                </span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </CardContent>
  </Card>
</template>
