<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

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
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('admin.reporting.categories.category') }}</TableHead>
            <TableHead class="text-right">{{ t('admin.reporting.categories.slots') }}</TableHead>
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
