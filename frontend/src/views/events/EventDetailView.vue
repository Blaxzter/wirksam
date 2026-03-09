<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { DateValue } from '@internationalized/date'
import { ArrowLeft, Check, ChevronDown, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import type {
  BookingListResponse,
  BookingRead,
  DutySlotListResponse,
  DutySlotRead,
  EventRead,
} from '@/client/types.gen'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { DatePicker } from '@/components/ui/date-picker'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { toastApiError } from '@/lib/api-errors'
import { formatDate } from '@/lib/format'
import { statusVariant } from '@/lib/status'
import { useAuthStore } from '@/stores/auth'
import { useBreadcrumbStore } from '@/stores/breadcrumb'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const eventId = computed(() => route.params.eventId as string)
const event = ref<EventRead | null>(null)
const statuses = ['draft', 'published', 'archived'] as const
const dutySlots = ref<DutySlotRead[]>([])
const myBookings = ref<BookingRead[]>([])
const loading = ref(false)
const showCreateSlotDialog = ref(false)

// Create slot form
const slotForm = ref({
  title: '',
  description: '',
  start_time: '',
  end_time: '',
  location: '',
  category: '',
  max_bookings: 5,
})
const slotDate = ref<DateValue>()

// Group slots by date
const slotsByDate = computed(() => {
  const groups: Record<string, DutySlotRead[]> = {}
  for (const slot of dutySlots.value) {
    const date = slot.date
    if (!groups[date]) groups[date] = []
    groups[date].push(slot)
  }
  // Sort by date
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
})

const myBookedSlotIds = computed(() => {
  return new Set(
    myBookings.value
      .filter((b) => b.status === 'confirmed')
      .map((b) => b.duty_slot_id),
  )
})

const getBookingForSlot = (slotId: string) => {
  return myBookings.value.find(
    (b) => b.duty_slot_id === slotId && b.status === 'confirmed',
  )
}

const isSlotFull = (slot: DutySlotRead) => {
  return (slot.current_bookings ?? 0) >= (slot.max_bookings ?? 1)
}

const loadEvent = async () => {
  loading.value = true
  try {
    const response = await get<{ data: EventRead }>({
      url: `/events/${eventId.value}`,
    })
    event.value = response.data

    // Set dynamic breadcrumbs
    breadcrumbStore.setBreadcrumbs([
      {
        title: 'Events',
        titleKey: 'duties.events.title',
        to: { name: 'events' },
      },
      {
        title: response.data.name,
      },
    ])
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'events' })
  } finally {
    loading.value = false
  }
}

const loadDutySlots = async () => {
  try {
    const response = await get<{ data: DutySlotListResponse }>({
      url: '/duty-slots/',
      query: { event_id: eventId.value, limit: 100 },
    })
    dutySlots.value = response.data.items
  } catch (error) {
    toastApiError(error)
  }
}

const loadMyBookings = async () => {
  try {
    const response = await get<{ data: BookingListResponse }>({
      url: '/bookings/me',
      query: { limit: 200 },
    })
    myBookings.value = response.data.items
  } catch (error) {
    toastApiError(error)
  }
}

const handleStatusChange = async (status: 'draft' | 'published' | 'archived') => {
  if (!event.value || event.value.status === status) return
  try {
    const response = await patch<{ data: EventRead }>({
      url: `/events/${event.value.id}`,
      body: { status },
    })
    event.value = response.data
    toast.success(t(`duties.events.statuses.${status}`))
  } catch (error) {
    toastApiError(error)
  }
}

const handleDeleteEvent = async () => {
  const confirmed = await confirmDestructive(t('duties.events.deleteConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/events/${eventId.value}` })
    toast.success(t('duties.events.delete'))
    router.push({ name: 'events' })
  } catch (error) {
    toastApiError(error)
  }
}

const handleCreateSlot = async () => {
  if (!slotDate.value) return
  try {
    await post({
      url: '/duty-slots/',
      body: {
        event_id: eventId.value,
        title: slotForm.value.title,
        description: slotForm.value.description || undefined,
        date: slotDate.value.toString(),
        start_time: slotForm.value.start_time || undefined,
        end_time: slotForm.value.end_time || undefined,
        location: slotForm.value.location || undefined,
        category: slotForm.value.category || undefined,
        max_bookings: slotForm.value.max_bookings,
      },
    })
    showCreateSlotDialog.value = false
    slotForm.value = {
      title: '',
      description: '',
      start_time: '',
      end_time: '',
      location: '',
      category: '',
      max_bookings: 5,
    }
    slotDate.value = undefined
    toast.success(t('duties.dutySlots.create'))
    await loadDutySlots()
  } catch (error) {
    toastApiError(error)
  }
}

const handleDeleteSlot = async (slot: DutySlotRead) => {
  const confirmed = await confirmDestructive(t('duties.dutySlots.deleteConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/duty-slots/${slot.id}` })
    toast.success(t('duties.dutySlots.delete'))
    await loadDutySlots()
  } catch (error) {
    toastApiError(error)
  }
}

const handleBookSlot = async (slot: DutySlotRead) => {
  try {
    await post({ url: '/bookings/', body: { duty_slot_id: slot.id } })
    toast.success(t('duties.bookings.bookSuccess'))
    await Promise.all([loadDutySlots(), loadMyBookings()])
  } catch (error) {
    toastApiError(error)
  }
}

const handleCancelBooking = async (slot: DutySlotRead) => {
  const booking = getBookingForSlot(slot.id)
  if (!booking) return

  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/bookings/${booking.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    await Promise.all([loadDutySlots(), loadMyBookings()])
  } catch (error) {
    toastApiError(error)
  }
}

onMounted(async () => {
  await loadEvent()
  await Promise.all([loadDutySlots(), loadMyBookings()])
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="event">
      <!-- Back button + Header -->
      <div class="space-y-4">
        <Button variant="ghost" size="sm" @click="router.push({ name: 'events' })">
          <ArrowLeft class="mr-2 h-4 w-4" />
          {{ t('common.actions.back') }}
        </Button>

        <div class="flex items-start justify-between">
          <div class="space-y-2">
            <div class="flex items-center gap-3">
              <h1 class="text-3xl font-bold">{{ event.name }}</h1>
              <DropdownMenu v-if="authStore.isAdmin">
                <DropdownMenuTrigger as-child>
                  <button class="inline-flex cursor-pointer items-center gap-1">
                    <Badge :variant="statusVariant(event.status)">
                      {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
                      <ChevronDown class="ml-1 h-3 w-3" />
                    </Badge>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    v-for="s in statuses"
                    :key="s"
                    :disabled="event.status === s"
                    @click="handleStatusChange(s)"
                  >
                    <Check v-if="event.status === s" class="mr-2 h-4 w-4" />
                    <span v-else class="mr-2 h-4 w-4" />
                    {{ t(`duties.events.statuses.${s}`) }}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <Badge v-else :variant="statusVariant(event.status)">
                {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
              </Badge>
            </div>
            <p v-if="event.description" class="text-muted-foreground">
              {{ event.description }}
            </p>
            <p class="text-sm text-muted-foreground">
              {{ formatDate(event.start_date) }} - {{ formatDate(event.end_date) }}
            </p>
          </div>
          <div v-if="authStore.isAdmin" class="flex gap-2">
            <Button
              variant="outline"
              @click="router.push({ name: 'event-edit', params: { eventId: event.id } })"
            >
              <Pencil class="mr-2 h-4 w-4" />
              {{ t('duties.events.edit') }}
            </Button>
            <Button @click="showCreateSlotDialog = true">
              <Plus class="mr-2 h-4 w-4" />
              {{ t('duties.events.detail.addSlot') }}
            </Button>
            <Button variant="destructive" size="icon" @click="handleDeleteEvent">
              <Trash2 class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <Separator />

      <!-- Duty Slots -->
      <div class="space-y-4">
        <h2 class="text-xl font-semibold">{{ t('duties.events.detail.slots') }}</h2>

        <div
          v-if="dutySlots.length === 0"
          class="text-center py-8 text-muted-foreground"
        >
          {{ t('duties.dutySlots.empty') }}
        </div>

        <div v-else class="space-y-6">
          <div v-for="[date, slots] in slotsByDate" :key="date" class="space-y-3">
            <h3 class="text-lg font-medium text-muted-foreground">
              {{ formatDate(date) }}
            </h3>
            <div class="grid gap-3 md:grid-cols-2">
              <Card v-for="slot in slots" :key="slot.id">
                <CardHeader class="pb-3">
                  <div class="flex items-start justify-between">
                    <CardTitle class="text-base">{{ slot.title }}</CardTitle>
                    <div class="flex items-center gap-2">
                      <Badge v-if="slot.category" variant="outline">
                        {{ slot.category }}
                      </Badge>
                      <Badge
                        :variant="isSlotFull(slot) ? 'destructive' : 'default'"
                      >
                        {{
                          isSlotFull(slot)
                            ? t('duties.dutySlots.full')
                            : t('duties.dutySlots.availability', {
                                current: slot.current_bookings ?? 0,
                                max: slot.max_bookings ?? 1,
                              })
                        }}
                      </Badge>
                    </div>
                  </div>
                  <CardDescription v-if="slot.description">
                    {{ slot.description }}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div class="flex items-center justify-between">
                    <div class="space-y-1 text-sm text-muted-foreground">
                      <div v-if="slot.start_time || slot.end_time">
                        {{ slot.start_time ?? '' }}{{ slot.start_time && slot.end_time ? ' - ' : '' }}{{ slot.end_time ?? '' }}
                      </div>
                      <div v-if="slot.location">{{ slot.location }}</div>
                    </div>
                    <div class="flex gap-2">
                      <Button
                        v-if="myBookedSlotIds.has(slot.id)"
                        variant="outline"
                        size="sm"
                        @click="handleCancelBooking(slot)"
                      >
                        {{ t('duties.bookings.cancel') }}
                      </Button>
                      <Button
                        v-else
                        size="sm"
                        :disabled="isSlotFull(slot)"
                        @click="handleBookSlot(slot)"
                      >
                        {{ t('duties.dutySlots.book') }}
                      </Button>
                      <Button
                        v-if="authStore.isAdmin"
                        variant="ghost"
                        size="icon"
                        class="h-8 w-8"
                        @click="handleDeleteSlot(slot)"
                      >
                        <Trash2 class="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Create Slot Dialog -->
    <Dialog v-model:open="showCreateSlotDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('duties.dutySlots.create') }}</DialogTitle>
          <DialogDescription>{{ t('duties.events.detail.addSlot') }}</DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit.prevent="handleCreateSlot">
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.title') }}</Label>
            <Input v-model="slotForm.title" required />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.description') }}</Label>
            <Input v-model="slotForm.description" />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.date') }}</Label>
            <DatePicker v-model="slotDate" :placeholder="t('duties.dutySlots.pickDate')" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.startTime') }}</Label>
              <Input v-model="slotForm.start_time" type="time" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.endTime') }}</Label>
              <Input v-model="slotForm.end_time" type="time" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.location') }}</Label>
              <Input v-model="slotForm.location" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.category') }}</Label>
              <Input v-model="slotForm.category" />
            </div>
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.maxBookings') }}</Label>
            <Input v-model.number="slotForm.max_bookings" type="number" min="1" required />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="showCreateSlotDialog = false">
              {{ t('common.actions.cancel') }}
            </Button>
            <Button type="submit">{{ t('common.actions.create') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>
