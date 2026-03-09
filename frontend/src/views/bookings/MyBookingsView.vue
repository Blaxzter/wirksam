<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import type { BookingListResponse, BookingRead, DutySlotRead } from '@/client/types.gen'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { toastApiError } from '@/lib/api-errors'
import { formatDate } from '@/lib/format'

const { t } = useI18n()
const { get, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

interface EnrichedBooking extends BookingRead {
  slot?: DutySlotRead
}

const bookings = ref<EnrichedBooking[]>([])
const loading = ref(false)

const statusVariant = (status?: string) => {
  switch (status) {
    case 'confirmed':
      return 'default'
    case 'cancelled':
      return 'secondary'
    default:
      return 'outline'
  }
}

const loadBookings = async () => {
  loading.value = true
  try {
    const response = await get<{ data: BookingListResponse }>({
      url: '/bookings/me',
      query: { limit: 200 },
    })
    const rawBookings = response.data.items

    // Enrich with slot details
    const enriched: EnrichedBooking[] = await Promise.all(
      rawBookings.map(async (booking) => {
        try {
          const slotResponse = await get<{ data: DutySlotRead }>({
            url: `/duty-slots/${booking.duty_slot_id}`,
          })
          return { ...booking, slot: slotResponse.data }
        } catch {
          return { ...booking }
        }
      }),
    )
    bookings.value = enriched
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

const handleCancel = async (booking: EnrichedBooking) => {
  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/bookings/${booking.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    await loadBookings()
  } catch (error) {
    toastApiError(error)
  }
}

onMounted(loadBookings)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="space-y-2">
      <h1 class="text-3xl font-bold">{{ t('duties.bookings.title') }}</h1>
      <p class="text-muted-foreground">{{ t('duties.bookings.subtitle') }}</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <!-- Empty -->
    <div
      v-else-if="bookings.length === 0"
      class="text-center py-12 text-muted-foreground"
    >
      {{ t('duties.bookings.empty') }}
    </div>

    <!-- Bookings Grid -->
    <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card v-for="booking in bookings" :key="booking.id">
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between">
            <CardTitle class="text-lg">
              {{ booking.slot?.title ?? booking.duty_slot_id }}
            </CardTitle>
            <Badge :variant="statusVariant(booking.status)">
              {{ t(`duties.bookings.statuses.${booking.status ?? 'confirmed'}`) }}
            </Badge>
          </div>
          <CardDescription v-if="booking.slot?.description">
            {{ booking.slot.description }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div class="space-y-2 text-sm text-muted-foreground">
            <div v-if="booking.slot?.date">
              {{ formatDate(booking.slot.date) }}
              <span v-if="booking.slot.start_time || booking.slot.end_time">
                {{ booking.slot.start_time ?? '' }}{{ booking.slot.start_time && booking.slot.end_time ? ' - ' : '' }}{{ booking.slot.end_time ?? '' }}
              </span>
            </div>
            <div v-if="booking.slot?.location">{{ booking.slot.location }}</div>
          </div>
          <div class="mt-4">
            <Button
              v-if="booking.status === 'confirmed'"
              variant="outline"
              size="sm"
              @click="handleCancel(booking)"
            >
              {{ t('duties.bookings.cancel') }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
