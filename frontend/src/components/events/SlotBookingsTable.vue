<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import type { SlotBookingEntry } from '@/client/types.gen'

defineProps<{
  bookings: SlotBookingEntry[]
  loading?: boolean
}>()

const { t, locale } = useI18n()
const authStore = useAuthStore()

const initials = (name: string | null | undefined, email: string | null | undefined): string => {
  if (name) {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }
  if (email) return email[0].toUpperCase()
  return '?'
}

const formatDateTime = (isoStr: string) => {
  return new Date(isoStr).toLocaleDateString(locale.value, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div>
    <div v-if="loading" class="text-sm text-muted-foreground py-3">
      {{ t('common.states.loading') }}
    </div>
    <p v-else-if="bookings.length === 0" class="text-sm text-muted-foreground py-2">
      {{ t('duties.dutySlots.detail.noBookings') }}
    </p>
    <div v-else class="rounded-md border overflow-x-auto">
      <Table class="table-fixed w-full">
        <TableHeader>
          <TableRow>
            <TableHead class="w-[45%]">{{
              t('duties.dutySlots.detail.userName')
            }}</TableHead>
            <TableHead v-if="authStore.isAdmin" class="w-[25%]">
              {{ t('duties.dutySlots.detail.userNotes') }}
            </TableHead>
            <TableHead class="w-[30%] text-right">
              {{ t('duties.dutySlots.detail.bookedAt') }}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="entry in bookings" :key="entry.id">
            <TableCell class="max-w-0">
              <div class="flex items-center gap-2.5 min-w-0">
                <Avatar class="h-7 w-7 shrink-0">
                  <AvatarImage v-if="entry.user_picture" :src="entry.user_picture" />
                  <AvatarFallback class="text-xs">
                    {{ initials(entry.user_name, entry.user_email) }}
                  </AvatarFallback>
                </Avatar>
                <div class="min-w-0">
                  <p class="font-medium truncate">{{ entry.user_name ?? '—' }}</p>
                  <p
                    v-if="authStore.isAdmin && entry.user_email"
                    class="text-xs text-muted-foreground truncate"
                  >
                    {{ entry.user_email }}
                  </p>
                </div>
              </div>
            </TableCell>
            <TableCell v-if="authStore.isAdmin" class="max-w-0">
              <span class="text-muted-foreground truncate block">{{ entry.notes ?? '—' }}</span>
            </TableCell>
            <TableCell class="text-right text-muted-foreground whitespace-nowrap">
              {{ formatDateTime(entry.created_at) }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
