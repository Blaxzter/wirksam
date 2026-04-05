<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  ArrowLeft,
  Bell,
  Calendar,
  Clock,
  ExternalLink,
  History,
  MapPin,
  Pencil,
  Plus,
  Tag,
  Trash2,
  Users,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import type { BookingReminder } from '@/stores/bookingReminder'
import { ALLOWED_OFFSETS, useBookingReminderStore } from '@/stores/bookingReminder'
import { useNotificationStore } from '@/stores/notification'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'

import ReminderEntryRow from '@/components/notifications/ReminderEntryRow.vue'
import SlotBookingsTable from '@/components/events/SlotBookingsTable.vue'

import type { BookingRead, DutySlotRead, SlotBookingEntry } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { get, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()
const { formatTime, formatDateLabel } = useFormatters()
const reminderStore = useBookingReminderStore()
const notificationStore = useNotificationStore()

const reminderChannels = computed(() => {
  const channels = ['email', 'push']
  if (notificationStore.telegramBinding?.is_verified) channels.push('telegram')
  return channels
})

const bookingId = computed(() => route.params.bookingId as string)

const loading = ref(true)
const booking = ref<BookingRead | null>(null)
const slot = ref<DutySlotRead | null>(null)
const slotBookings = ref<SlotBookingEntry[]>([])
const eventName = ref<string | null>(null)

// Notes
const editingNotes = ref(false)
const notesValue = ref('')
const savingNotes = ref(false)

// Reminders
const bookingReminders = ref<BookingReminder[]>([])
const loadingReminderIds = ref(new Set<string>())

const activeReminders = computed(() =>
  bookingReminders.value.filter((r) => r.status === 'pending'),
)

const pastReminders = computed(() =>
  bookingReminders.value.filter((r) => r.status !== 'pending'),
)

const hasAnyReminders = computed(() => bookingReminders.value.length > 0)

const availableReminderOffsets = computed(() =>
  ALLOWED_OFFSETS.filter(
    (o) => !bookingReminders.value.some((r) => r.offset_minutes === o && r.status === 'pending'),
  ),
)

function getReminderOffsetLabel(offset: number): string {
  return t(`notifications.reminders.offset.${offset}`)
}

const timeDisplay = computed(() => {
  const s = slot.value
  if (!s) return null
  const parts: string[] = []
  if (s.start_time) parts.push(formatTime(s.start_time))
  if (s.end_time) parts.push(formatTime(s.end_time))
  return parts.length > 0 ? parts.join(' – ') : null
})

const isConfirmed = computed(() => booking.value?.status === 'confirmed')

const isInPast = computed(() => {
  const s = slot.value
  if (!s) return false
  const slotDate = new Date(s.date + 'T' + (s.end_time ?? s.start_time ?? '23:59'))
  return slotDate < new Date()
})

// ── Data loading ──────────────────────────────────────────────

async function loadData() {
  loading.value = true
  try {
    // Load booking
    const bookingRes = await get<{ data: BookingRead }>({
      url: `/bookings/${bookingId.value}`,
    })
    booking.value = bookingRes.data
    notesValue.value = bookingRes.data.notes ?? ''

    // Load slot if booking has one
    if (bookingRes.data.duty_slot_id) {
      const [slotRes, bookingsRes, reminders] = await Promise.all([
        get<{ data: DutySlotRead }>({
          url: `/duty-slots/${bookingRes.data.duty_slot_id}`,
        }),
        get<{ data: SlotBookingEntry[] }>({
          url: `/duty-slots/${bookingRes.data.duty_slot_id}/bookings`,
        }),
        reminderStore.fetchBookingReminders(bookingId.value),
        notificationStore.fetchTelegramBinding(),
      ])
      slot.value = slotRes.data
      slotBookings.value = bookingsRes.data
      bookingReminders.value = reminders

      // Get event name from slot
      if (slotRes.data.event_id) {
        try {
          const eventRes = await get<{ data: { name: string } }>({
            url: `/events/${slotRes.data.event_id}`,
          })
          eventName.value = eventRes.data.name
        } catch {
          // Non-critical
        }
      }
    }
  } catch {
    toast.error(t('duties.bookings.detail.loadFailed'))
    router.replace({ name: 'my-bookings' })
  } finally {
    loading.value = false
  }
}

// ── Actions ───────────────────────────────────────────────────

async function saveNotes() {
  if (!booking.value) return
  savingNotes.value = true
  try {
    await patch({
      url: `/bookings/${booking.value.id}`,
      body: { notes: notesValue.value || null },
    })
    booking.value = { ...booking.value, notes: notesValue.value || null }
    editingNotes.value = false
    toast.success(t('duties.dutySlots.detail.notesSaved'))

    // Reload bookings table
    if (booking.value.duty_slot_id) {
      const res = await get<{ data: SlotBookingEntry[] }>({
        url: `/duty-slots/${booking.value.duty_slot_id}/bookings`,
      })
      slotBookings.value = res.data
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    savingNotes.value = false
  }
}

async function cancelBooking() {
  if (!booking.value) return
  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return
  try {
    await del({ url: `/bookings/${booking.value.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    router.replace({ name: 'my-bookings' })
  } catch (error) {
    toastApiError(error)
  }
}

async function addReminder(offset: number) {
  if (!booking.value) return
  try {
    const reminder = await reminderStore.addBookingReminder(booking.value.id, offset, ['push'])
    bookingReminders.value = [...bookingReminders.value, reminder].sort(
      (a, b) => a.offset_minutes - b.offset_minutes,
    )
  } catch {
    toast.error(t('notifications.reminders.perBooking.addFailed'))
  }
}

async function toggleReminderChannel(reminderId: string, channel: string) {
  const reminder = bookingReminders.value.find((r) => r.id === reminderId)
  if (!reminder) return
  const hasChannel = reminder.channels.includes(channel)
  if (hasChannel && reminder.channels.length === 1) return // Must keep at least one

  // Optimistic update: remove old, re-add with new channels
  const newChannels = hasChannel
    ? reminder.channels.filter((c) => c !== channel)
    : [...reminder.channels, channel]

  loadingReminderIds.value.add(reminderId)
  let newId: string | null = null
  try {
    // Delete and re-create with new channels (no PATCH endpoint for reminders)
    await reminderStore.deleteReminder(reminderId)
    if (!booking.value) return
    const newReminder = await reminderStore.addBookingReminder(
      booking.value.id,
      reminder.offset_minutes,
      newChannels,
    )
    newId = newReminder.id
    bookingReminders.value = bookingReminders.value
      .filter((r) => r.id !== reminderId)
      .concat(newReminder)
      .sort((a, b) => a.offset_minutes - b.offset_minutes)
  } catch {
    toast.error(t('notifications.reminders.perBooking.addFailed'))
    // Reload to recover
    bookingReminders.value = await reminderStore.fetchBookingReminders(booking.value!.id)
  } finally {
    loadingReminderIds.value.delete(reminderId)
    if (newId) loadingReminderIds.value.delete(newId)
  }
}

async function removeReminder(reminderId: string) {
  loadingReminderIds.value.add(reminderId)
  try {
    await reminderStore.deleteReminder(reminderId)
    bookingReminders.value = bookingReminders.value.filter((r) => r.id !== reminderId)
  } catch {
    toast.error(t('notifications.reminders.perBooking.removeFailed'))
  } finally {
    loadingReminderIds.value.delete(reminderId)
  }
}

function navigateToEvent() {
  const eventId = slot.value?.event_id
  if (eventId) {
    router.push({ name: 'event-detail', params: { eventId } })
  }
}

onMounted(loadData)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <!-- Back + Header -->
    <div>
      <Button
        data-testid="btn-back"
        variant="ghost"
        size="sm"
        class="mb-2 -ml-2 text-muted-foreground"
        @click="router.push({ name: 'my-bookings' })"
      >
        <ArrowLeft class="mr-1.5 h-4 w-4" />
        {{ t('duties.bookings.title') }}
      </Button>

      <div v-if="loading" class="flex items-center justify-center py-12">
        <div class="border-primary h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
      </div>

      <template v-else-if="booking && slot">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h1 data-testid="page-heading" class="text-2xl font-bold tracking-tight">{{ slot.title }}</h1>
            <p v-if="eventName" class="text-muted-foreground mt-1">{{ eventName }}</p>
          </div>
          <Badge data-testid="booking-status" :variant="isConfirmed ? 'default' : 'destructive'" class="mt-1">
            {{ t(`duties.bookings.statuses.${booking.status ?? 'confirmed'}`) }}
          </Badge>
        </div>
      </template>
    </div>

    <template v-if="!loading && booking && slot">
      <!-- Past event banner -->
      <div
        v-if="isInPast"
        class="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-800 dark:bg-amber-950/20"
      >
        <History class="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
        <p class="text-sm font-medium text-amber-800 dark:text-amber-200">
          {{ t('duties.bookings.detail.pastEvent') }}
        </p>
      </div>

      <!-- ── Slot Info Card ──────────────────────────────────── -->
      <Card data-testid="section-slot-info">
        <CardContent class="pt-6">
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="flex items-start gap-2.5">
              <Calendar class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">{{ t('duties.dutySlots.detail.date') }}</p>
                <p class="text-sm font-medium">
                  {{ formatDateLabel(slot.date, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) }}
                </p>
              </div>
            </div>
            <div v-if="timeDisplay" class="flex items-start gap-2.5">
              <Clock class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">{{ t('duties.dutySlots.detail.time') }}</p>
                <p class="text-sm font-medium font-mono">{{ timeDisplay }}</p>
              </div>
            </div>
            <div v-if="slot.location" class="flex items-start gap-2.5">
              <MapPin class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">{{ t('duties.dutySlots.detail.location') }}</p>
                <p class="text-sm font-medium">{{ slot.location }}</p>
              </div>
            </div>
            <div v-if="slot.category" class="flex items-start gap-2.5">
              <Tag class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">{{ t('duties.dutySlots.detail.category') }}</p>
                <p class="text-sm font-medium">{{ slot.category }}</p>
              </div>
            </div>
            <div class="flex items-start gap-2.5">
              <Users class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">{{ t('duties.dutySlots.detail.capacity') }}</p>
                <p class="text-sm font-medium">
                  {{ t('duties.dutySlots.detail.capacityValue', { current: slot.current_bookings ?? 0, max: slot.max_bookings ?? 1 }) }}
                </p>
              </div>
            </div>
          </div>

          <p v-if="slot.description" class="text-sm text-muted-foreground mt-4 whitespace-pre-line">
            {{ slot.description }}
          </p>

          <div class="flex items-center gap-2 mt-4 pt-4 border-t">
            <Button v-if="eventName" variant="outline" size="sm" @click="navigateToEvent">
              <ExternalLink class="mr-1.5 h-3.5 w-3.5" />
              {{ t('duties.dutySlots.detail.viewEvent') }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <!-- ── My Notes Card ───────────────────────────────────── -->
      <Card v-if="isConfirmed" data-testid="section-notes">
        <CardHeader>
          <div class="flex items-center justify-between">
            <CardTitle class="text-base">{{ t('duties.dutySlots.detail.myNotes') }}</CardTitle>
            <Button
              v-if="!editingNotes"
              variant="ghost"
              size="sm"
              class="h-7 text-xs"
              @click="editingNotes = true"
            >
              <Pencil class="mr-1 h-3 w-3" />
              {{ t('common.actions.edit') }}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="editingNotes" class="space-y-3">
            <Textarea
              v-model="notesValue"
              :placeholder="t('duties.dutySlots.detail.notesPlaceholder')"
              rows="3"
            />
            <div class="flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                @click="() => { editingNotes = false; notesValue = booking?.notes ?? '' }"
              >
                {{ t('common.actions.cancel') }}
              </Button>
              <Button size="sm" :disabled="savingNotes" @click="saveNotes">
                {{ t('common.actions.save') }}
              </Button>
            </div>
          </div>
          <p v-else class="text-sm text-muted-foreground">
            {{ booking?.notes || t('duties.dutySlots.detail.noNotes') }}
          </p>
        </CardContent>
      </Card>

      <!-- ── Reminders Card ──────────────────────────────────── -->
      <Card v-if="isConfirmed || hasAnyReminders" data-testid="section-reminders">
        <CardHeader>
          <div class="flex items-center gap-2">
            <Bell class="h-4 w-4 text-amber-600 dark:text-amber-400" />
            <CardTitle class="text-base">{{ t('notifications.reminders.perBooking.title') }}</CardTitle>
          </div>
          <CardDescription>
            {{ t('notifications.reminders.description') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-3">
          <ReminderEntryRow
            v-for="reminder in activeReminders"
            :key="reminder.offset_minutes"
            :offset-label="getReminderOffsetLabel(reminder.offset_minutes)"
            :channels="reminder.channels"
            :available-channels="reminderChannels"
            :loading="loadingReminderIds.has(reminder.id)"
            @toggle-channel="(ch) => toggleReminderChannel(reminder.id, ch)"
            @remove="removeReminder(reminder.id)"
          />

          <!-- Past reminders (sent/expired) — read-only, muted -->
          <ReminderEntryRow
            v-for="reminder in pastReminders"
            :key="reminder.id"
            :offset-label="getReminderOffsetLabel(reminder.offset_minutes)"
            :channels="reminder.channels"
            :available-channels="reminderChannels"
            readonly
            :status-label="t(`notifications.reminders.perBooking.${reminder.status}`)"
          />

          <DropdownMenu v-if="availableReminderOffsets.length > 0">
            <DropdownMenuTrigger as-child>
              <Button variant="outline" size="sm" class="h-8 gap-1">
                <Plus :size="14" />
                {{ t('notifications.reminders.perBooking.add') }}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem
                v-for="offset in availableReminderOffsets"
                :key="offset"
                @click="addReminder(offset)"
              >
                {{ getReminderOffsetLabel(offset) }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <p
            v-if="activeReminders.length === 0 && availableReminderOffsets.length === 0"
            class="text-muted-foreground text-sm"
          >
            {{ t('notifications.reminders.perBooking.empty') }}
          </p>
        </CardContent>
      </Card>

      <!-- ── Co-bookers Card ─────────────────────────────────── -->
      <Card>
        <CardHeader>
          <CardTitle class="text-base">{{ t('duties.dutySlots.detail.bookedUsers') }}</CardTitle>
        </CardHeader>
        <CardContent>
          <SlotBookingsTable :bookings="slotBookings" />
        </CardContent>
      </Card>

      <!-- ── Danger Zone ─────────────────────────────────────── -->
      <div v-if="isConfirmed" class="flex justify-end pt-2">
        <Button data-testid="btn-cancel-booking" variant="destructive" size="sm" @click="cancelBooking">
          <Trash2 class="mr-1.5 h-4 w-4" />
          {{ t('duties.bookings.cancel') }}
        </Button>
      </div>
    </template>
  </div>
</template>
