<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import type { CategoryBreakdown } from '@/client/types.gen'

defineProps<{
  categories: CategoryBreakdown[]
}>()

const { t } = useI18n()
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ t('admin.reporting.categories.title') }}</CardTitle>
      <CardDescription>{{ t('admin.reporting.categories.description') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <!-- Phones: one stacked row per category; five columns would scroll sideways. -->
      <ul class="divide-y sm:hidden">
        <li
          v-for="(cat, idx) in categories"
          :key="idx"
          class="space-y-1.5 py-3 first:pt-0 last:pb-0"
        >
          <div class="flex items-center justify-between gap-3">
            <Badge variant="outline" class="min-w-0 truncate">
              {{ cat.category || t('admin.reporting.categories.uncategorized') }}
            </Badge>
            <span class="shrink-0 text-sm font-medium tabular-nums">{{ cat.fill_rate }}%</span>
          </div>
          <p class="text-xs text-muted-foreground tabular-nums">
            {{ t('admin.reporting.categories.shifts') }} {{ cat.slot_count }} ·
            {{ t('admin.reporting.categories.booked') }} {{ cat.confirmed_bookings }} ·
            {{ t('admin.reporting.categories.capacity') }} {{ cat.total_capacity }}
          </p>
        </li>
      </ul>
      <Table class="max-sm:hidden">
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('admin.reporting.categories.category') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.categories.shifts') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.categories.capacity') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.categories.booked') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.categories.fillRate') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="(cat, idx) in categories" :key="idx">
            <TableCell>
              <Badge variant="outline">
                {{ cat.category || t('admin.reporting.categories.uncategorized') }}
              </Badge>
            </TableCell>
            <TableCell class="text-right tabular-nums">{{ cat.slot_count }}</TableCell>
            <TableCell class="text-right tabular-nums">{{ cat.total_capacity }}</TableCell>
            <TableCell class="text-right tabular-nums">{{ cat.confirmed_bookings }}</TableCell>
            <TableCell class="text-right tabular-nums font-medium">
              {{ cat.fill_rate }}%
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </CardContent>
  </Card>
</template>
