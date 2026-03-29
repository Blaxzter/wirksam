<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

import type { TopVolunteer } from '@/client/types.gen'

defineProps<{
  volunteers: TopVolunteer[]
}>()

const { t } = useI18n()
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ t('admin.reporting.topVolunteers.title') }}</CardTitle>
      <CardDescription>{{ t('admin.reporting.topVolunteers.description') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('admin.reporting.topVolunteers.name') }}</TableHead>
            <TableHead class="text-right">
              {{ t('admin.reporting.topVolunteers.bookings') }}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="vol in volunteers" :key="vol.user_id">
            <TableCell>
              <div>{{ vol.name || vol.email || '—' }}</div>
              <div v-if="vol.name && vol.email" class="text-xs text-muted-foreground">
                {{ vol.email }}
              </div>
            </TableCell>
            <TableCell class="text-right tabular-nums font-medium">
              {{ vol.booking_count }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </CardContent>
  </Card>
</template>
