<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Calendar, Clock, ExternalLink, MapPin, Pencil, Tag, Users } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Separator from '@/components/ui/separator/Separator.vue'
import { Textarea } from '@/components/ui/textarea'

import SlotBookingsTable from '@/components/events/SlotBookingsTable.vue'

import type { BookingRead, DutySlotRead, SlotBookingEntry } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const props = defineProps<{
  /** Pass a full slot object (from EventDetailView) */
  dutySlot?: DutySlotRead | null
  /** Or pass just an ID to fetch the slot (from MyBookingsView) */
  slotId?: string | null
  eventName?: string | null
  /** The current user's booking for this slot (enables notes editing) */
  myBooking?: BookingRead | null
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'booking-updated': []
}>()

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const router = useRouter()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const fetchedSlot = ref<DutySlotRead | null>(null)
const slotBookings = ref<SlotBookingEntry[]>([])
const loadingSlot = ref(false)
const loadingBookings = ref(false)

// Notes editing
const editingNotes = ref(false)
const notesValue = ref('')
const savingNotes = ref(false)

const saveNotes = async () => {
  if (!props.myBooking) return
  savingNotes.value = true
  try {
    await patch({
      url: `/bookings/${props.myBooking.id}`,
      body: { notes: notesValue.value || null },
    })
    editingNotes.value = false
    toast.success(t('duties.dutySlots.detail.notesSaved'))
    emit('booking-updated')
    // Reload bookings table to reflect updated notes
    const slotId = resolvedSlot.value?.id
    if (slotId) {
      const response = await get<{ data: SlotBookingEntry[] }>({
        url: `/duty-slots/${slotId}/bookings`,
      })
      slotBookings.value = response.data
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    savingNotes.value = false
  }
}

const dialogOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

/** The resolved slot — either from props or fetched by ID */
const resolvedSlot = computed(() => props.dutySlot ?? fetchedSlot.value)

// Load data when dialog opens
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      slotBookings.value = []
      fetchedSlot.value = null
      editingNotes.value = false
      return
    }

    // Initialize notes from booking
    notesValue.value = props.myBooking?.notes ?? ''

    // If we only have a slotId, fetch the full slot
    const slotId = props.dutySlot?.id ?? props.slotId
    if (!props.dutySlot && props.slotId) {
      loadingSlot.value = true
      try {
        const response = await get<{ data: DutySlotRead }>({
          url: `/duty-slots/${props.slotId}`,
        })
        fetchedSlot.value = response.data
      } catch {
        fetchedSlot.value = null
      } finally {
        loadingSlot.value = false
      }
    }

    // Load bookings
    if (slotId) {
      loadingBookings.value = true
      try {
        const response = await get<{ data: SlotBookingEntry[] }>({
          url: `/duty-slots/${slotId}/bookings`,
        })
        slotBookings.value = response.data
      } catch {
        slotBookings.value = []
      } finally {
        loadingBookings.value = false
      }
    }
  },
)

const timeDisplay = computed(() => {
  const s = resolvedSlot.value
  if (!s) return null
  const parts: string[] = []
  if (s.start_time) parts.push(formatTime(s.start_time))
  if (s.end_time) parts.push(formatTime(s.end_time))
  return parts.length > 0 ? parts.join(' – ') : null
})

const isSlotFull = computed(() => {
  const s = resolvedSlot.value
  if (!s) return true
  return (s.current_bookings ?? 0) >= (s.max_bookings ?? 1)
})

const canBook = computed(() => {
  return !props.myBooking && !isSlotFull.value
})

const bookingInProgress = ref(false)

const handleBook = async () => {
  const slot = resolvedSlot.value
  if (!slot || isSlotFull.value) return
  bookingInProgress.value = true
  try {
    await post({ url: '/bookings/', body: { duty_slot_id: slot.id } })
    toast.success(t('duties.bookings.bookSuccess'))
    emit('booking-updated')
    dialogOpen.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    bookingInProgress.value = false
  }
}

const handleCancelBooking = async () => {
  if (!props.myBooking) return
  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return
  bookingInProgress.value = true
  try {
    await del({ url: `/bookings/${props.myBooking.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    emit('booking-updated')
    dialogOpen.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    bookingInProgress.value = false
  }
}

const navigateToEvent = () => {
  const eventId = resolvedSlot.value?.event_id
  if (eventId) {
    dialogOpen.value = false
    router.push({ name: 'event-detail', params: { eventId } })
  }
}
</script>

<template>
  <Dialog v-model:open="dialogOpen">
    <DialogContent class="sm:max-w-lg max-h-[85vh] overflow-y-auto">
      <DialogHeader>
        <div class="flex items-center justify-between gap-2 pr-6">
          <DialogTitle>{{ t('duties.dutySlots.detail.title') }}</DialogTitle>
          <Badge v-if="resolvedSlot" variant="outline" class="text-xs shrink-0">
            {{ resolvedSlot.current_bookings ?? 0 }} / {{ resolvedSlot.max_bookings ?? 1 }}
          </Badge>
        </div>
        <DialogDescription v-if="eventName">
          {{ eventName }}
        </DialogDescription>
      </DialogHeader>

      <!-- Loading state when fetching slot by ID -->
      <div v-if="loadingSlot" class="text-center py-8 text-muted-foreground">
        {{ t('common.states.loading') }}
      </div>

      <template v-else-if="resolvedSlot">
        <!-- Slot info grid -->
        <div class="space-y-4">
          <!-- Date & Time -->
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="flex items-start gap-2.5">
              <Calendar class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">
                  {{ t('duties.dutySlots.detail.date') }}
                </p>
                <p class="text-sm font-medium">{{ formatDateLabel(resolvedSlot.date, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) }}</p>
              </div>
            </div>
            <div v-if="timeDisplay" class="flex items-start gap-2.5">
              <Clock class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">
                  {{ t('duties.dutySlots.detail.time') }}
                </p>
                <p class="text-sm font-medium font-mono">{{ timeDisplay }}</p>
              </div>
            </div>
          </div>

          <!-- Location & Category -->
          <div
            v-if="resolvedSlot.location || resolvedSlot.category"
            class="grid gap-3 sm:grid-cols-2"
          >
            <div v-if="resolvedSlot.location" class="flex items-start gap-2.5">
              <MapPin class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">
                  {{ t('duties.dutySlots.detail.location') }}
                </p>
                <p class="text-sm font-medium">{{ resolvedSlot.location }}</p>
              </div>
            </div>
            <div v-if="resolvedSlot.category" class="flex items-start gap-2.5">
              <Tag class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p class="text-xs text-muted-foreground">
                  {{ t('duties.dutySlots.detail.category') }}
                </p>
                <p class="text-sm font-medium">{{ resolvedSlot.category }}</p>
              </div>
            </div>
          </div>

          <!-- Capacity -->
          <div class="flex items-start gap-2.5">
            <Users class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div>
              <p class="text-xs text-muted-foreground">
                {{ t('duties.dutySlots.detail.capacity') }}
              </p>
              <p class="text-sm font-medium">
                {{
                  t('duties.dutySlots.detail.capacityValue', {
                    current: resolvedSlot.current_bookings ?? 0,
                    max: resolvedSlot.max_bookings ?? 1,
                  })
                }}
              </p>
            </div>
          </div>

          <!-- Description -->
          <div v-if="resolvedSlot.description">
            <p class="text-xs text-muted-foreground mb-1">
              {{ t('duties.dutySlots.detail.description') }}
            </p>
            <p class="text-sm whitespace-pre-line">{{ resolvedSlot.description }}</p>
          </div>

          <!-- My notes (when user has a booking) -->
          <div v-if="myBooking">
            <div class="flex items-center justify-between mb-1.5">
              <p class="text-xs text-muted-foreground">
                {{ t('duties.dutySlots.detail.myNotes') }}
              </p>
              <Button
                v-if="!editingNotes"
                variant="ghost"
                size="sm"
                class="h-6 px-2 text-xs"
                @click="editingNotes = true"
              >
                <Pencil class="mr-1 h-3 w-3" />
                {{ t('common.actions.edit') }}
              </Button>
            </div>
            <div v-if="editingNotes" class="space-y-2">
              <Textarea
                v-model="notesValue"
                :placeholder="t('duties.dutySlots.detail.notesPlaceholder')"
                rows="2"
              />
              <div class="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  @click="
                    () => {
                      editingNotes = false
                      notesValue = myBooking?.notes ?? ''
                    }
                  "
                >
                  {{ t('common.actions.cancel') }}
                </Button>
                <Button size="sm" :disabled="savingNotes" @click="saveNotes">
                  {{ t('common.actions.save') }}
                </Button>
              </div>
            </div>
            <p v-else class="text-sm">
              {{ myBooking.notes || t('duties.dutySlots.detail.noNotes') }}
            </p>
          </div>

          <!-- Extensibility slot: future fields (materials, protection, etc.) go here -->
          <slot name="extra-details" />

          <Separator />

          <!-- Booked users table -->
          <div>
            <h3 class="text-sm font-semibold mb-2">
              {{ t('duties.dutySlots.detail.bookedUsers') }}
            </h3>
            <SlotBookingsTable :bookings="slotBookings" :loading="loadingBookings" />
          </div>

          <!-- Extensibility slot: additional sections below the table -->
          <slot name="extra-sections" />
        </div>

        <!-- Footer actions -->
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-2">
          <div class="flex items-center gap-2">
            <Button
              v-if="eventName"
              variant="outline"
              size="sm"
              class="w-full sm:w-auto"
              @click="navigateToEvent"
            >
              <ExternalLink class="mr-1.5 h-3.5 w-3.5" />
              {{ t('duties.dutySlots.detail.viewEvent') }}
            </Button>
          </div>
          <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
            <Button
              v-if="canBook"
              size="sm"
              class="w-full sm:w-auto"
              :disabled="bookingInProgress"
              @click="handleBook"
            >
              {{ t('duties.dutySlots.book') }}
            </Button>
            <Button
              v-if="myBooking"
              variant="destructive"
              size="sm"
              class="w-full sm:w-auto"
              :disabled="bookingInProgress"
              @click="handleCancelBooking"
            >
              {{ t('duties.bookings.cancel') }}
            </Button>
          </div>
        </div>
      </template>
    </DialogContent>
  </Dialog>
</template>
