<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Minus, Plus, Scale, Ticket, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'
import Label from '@/components/ui/label/Label.vue'
import {
  NumberField,
  NumberFieldContent,
  NumberFieldDecrement,
  NumberFieldIncrement,
  NumberFieldInput,
} from '@/components/ui/number-field'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

import EventMemberPicker from '@/components/events/EventMemberPicker.vue'

import type { EventMemberRead, VoucherBalance, VoucherEntryRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { correctionTakeAwayMax } from '@/lib/vouchers'

/**
 * Add or take away vouchers by hand, with a reason. The amount is always typed
 * as a positive number and the direction picked beside it, because a phone's
 * number pad often has no minus key.
 *
 * Taking away is capped at what the person can still redeem: a balance never
 * goes below zero, and the server refuses anything more (`409
 * voucher.correction_exceeds_available`), which still arrives as a toast when
 * someone redeemed in the meantime.
 */
const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  eventId: string
  /** Who can be picked. Ignored when `userId` or `entry` fixes the person. */
  members: EventMemberRead[]
  /** Fix the person (opened from their row). */
  userId?: string | null
  /** Their name, shown in place of the picker. */
  userName?: string | null
  /** Edit this correction instead of adding one. */
  entry?: VoucherEntryRead | null
  /** Everyone's balances, to say what the chosen person has before changing it. */
  balances?: VoucherBalance[]
}>()

const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()
const { post, patch } = useAuthenticatedClient()

/** The server's limit, either way. */
const MAX_ADJUSTMENT = 999

const picked = ref<EventMemberRead | null>(null)
const direction = ref<'add' | 'take'>('add')
/** `undefined` once the field is emptied: reka's number field reports no number then. */
const amount = ref<number | undefined>(1)
const note = ref('')
const saving = ref(false)
/** A save was tried: from then on, say next to each field what is missing. */
const attempted = ref(false)

const isEdit = computed(() => !!props.entry)
const lockedUser = computed(() => (props.entry ? null : (props.userId ?? null)))
const personId = computed(() => lockedUser.value ?? picked.value?.user_id ?? null)
const showPicker = computed(() => !isEdit.value && !lockedUser.value)

watch(open, (isOpen) => {
  if (!isOpen) return
  picked.value = null
  direction.value = (props.entry?.amount ?? 1) < 0 ? 'take' : 'add'
  amount.value = Math.abs(props.entry?.amount ?? 1) || 1
  note.value = props.entry?.note ?? ''
  attempted.value = false
})

/** The chosen person's vouchers now, from the overview. */
const current = computed(() => {
  const id = props.entry ? (props.userId ?? null) : personId.value
  return id ? (props.balances?.find((b) => b.user_id === id) ?? null) : null
})
const currentName = computed(() =>
  current.value ? (current.value.name ?? current.value.email ?? '?') : '',
)
/** The most "Take away" may take; `null` while nobody (or nobody known) is chosen. */
const takeMax = computed(() =>
  current.value ? correctionTakeAwayMax(current.value.available, props.entry?.amount ?? 0) : null,
)
const taking = computed(() => direction.value === 'take')
const amountMax = computed(() =>
  taking.value && takeMax.value !== null
    ? Math.max(1, Math.min(MAX_ADJUSTMENT, takeMax.value))
    : MAX_ADJUSTMENT,
)

// Switching to "Take away", or picking someone with less, brings the amount
// down to what can be taken, so the stepper never starts past its end.
watch([taking, takeMax], () => {
  if (!taking.value || takeMax.value === null || takeMax.value < 1) return
  if (amount.value !== undefined && amount.value > takeMax.value) amount.value = takeMax.value
})

const personMissing = computed(() => !isEdit.value && !personId.value)
const amountInvalid = computed(
  () =>
    amount.value === undefined ||
    !Number.isInteger(amount.value) ||
    amount.value < 1 ||
    amount.value > MAX_ADJUSTMENT,
)
/** Taking away more than is left, which the server would refuse. */
const overCap = computed(
  () =>
    taking.value &&
    takeMax.value !== null &&
    amount.value !== undefined &&
    amount.value > takeMax.value,
)
const noteMissing = computed(() => note.value.trim().length === 0)
const valid = computed(
  () => !personMissing.value && !amountInvalid.value && !overCap.value && !noteMissing.value,
)

/** What they can redeem after saving; an edit replaces its old amount. */
const availableAfter = computed(() => {
  if (!current.value || amountInvalid.value || overCap.value) return null
  const n = amount.value as number
  const signed = taking.value ? -n : n
  return Math.max(0, current.value.available - (props.entry?.amount ?? 0) + signed)
})

async function save() {
  if (!valid.value) {
    attempted.value = true
    return
  }
  saving.value = true
  const n = amount.value as number
  const signed = direction.value === 'take' ? -n : n
  try {
    if (props.entry) {
      await patch({
        url: `/events/${props.eventId}/vouchers/adjustments/${props.entry.id}`,
        body: { amount: signed, note: note.value.trim() },
      })
    } else {
      await post({
        url: `/events/${props.eventId}/vouchers/adjustments`,
        body: { user_id: personId.value, amount: signed, note: note.value.trim() },
      })
    }
    toast.success(t('vouchers.admin.saved'))
    open.value = false
    emit('saved')
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent
      dialog-class="sm:max-w-md"
      keep-keyboard-closed
      data-testid="voucher-adjustment-dialog"
    >
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="flex items-center gap-2">
          <Scale class="size-5" />
          {{ isEdit ? t('vouchers.admin.editCorrection') : t('vouchers.admin.addCorrection') }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="text-left">
          {{ t('vouchers.admin.correctionHint') }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-4 pb-2">
        <div v-if="showPicker" class="space-y-2">
          <EventMemberPicker
            v-if="!picked"
            :members="members"
            :label="t('vouchers.admin.person')"
            :placeholder="t('teams.roster.addPlaceholder')"
            input-id="voucher-adjustment-person"
            :action-hint="t('vouchers.redeem.enterToPick')"
            testid="voucher-adjustment-person"
            @pick="(m) => (picked = m)"
          />
          <template v-else>
            <Label>{{ t('vouchers.admin.person') }}</Label>
            <div>
              <Badge variant="secondary" class="gap-1 py-1 pr-1 pl-2.5 text-sm">
                <span class="max-w-60 truncate">{{ picked.name || picked.email || '?' }}</span>
                <button
                  type="button"
                  class="rounded-full p-0.5 hover:bg-muted-foreground/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  :aria-label="
                    t('duties.events.members.remove', { name: picked.name || picked.email || '?' })
                  "
                  @click="picked = null"
                >
                  <X class="size-3.5" />
                </button>
              </Badge>
            </div>
          </template>
        </div>
        <div
          v-else-if="userName || current"
          class="flex items-center gap-3 rounded-lg border bg-card px-3 py-2.5"
          data-testid="voucher-adjustment-person-row"
        >
          <span class="min-w-0 flex-1 truncate text-sm font-semibold">
            <span class="sr-only">{{ t('vouchers.admin.person') }}:</span>
            {{ userName || currentName }}
          </span>
          <Badge
            v-if="current"
            class="shrink-0 gap-1 tabular-nums"
            data-testid="voucher-adjustment-current"
          >
            <Ticket class="size-3.5" aria-hidden="true" />
            {{ t('vouchers.available', { n: current.available }, current.available) }}
          </Badge>
        </div>
        <p
          v-if="showPicker && attempted && personMissing"
          class="-mt-2 text-sm text-destructive"
          data-testid="voucher-adjustment-person-error"
        >
          {{ t('vouchers.admin.personRequired') }}
        </p>
        <p
          v-if="showPicker && current"
          class="-mt-2 text-sm text-muted-foreground"
          data-testid="voucher-adjustment-current"
        >
          {{
            t(
              'vouchers.redeem.hasAvailable',
              { name: currentName, n: current.available },
              current.available,
            )
          }}
        </p>

        <div class="space-y-2">
          <Label for="voucher-adjustment-amount">{{ t('vouchers.admin.amount') }}</Label>
          <div class="flex flex-wrap items-center gap-3">
            <ToggleGroup
              type="single"
              variant="outline"
              :model-value="direction"
              @update:model-value="(v) => v && (direction = v as 'add' | 'take')"
            >
              <ToggleGroupItem value="add" data-testid="voucher-adjustment-add">
                <Plus class="size-4" />
                {{ t('vouchers.admin.add') }}
              </ToggleGroupItem>
              <ToggleGroupItem value="take" data-testid="voucher-adjustment-take">
                <Minus class="size-4" />
                {{ t('vouchers.admin.takeAway') }}
              </ToggleGroupItem>
            </ToggleGroup>
            <NumberField
              id="voucher-adjustment-amount"
              v-model="amount"
              :min="1"
              :max="amountMax"
              class="w-32"
              data-testid="voucher-adjustment-amount"
            >
              <NumberFieldContent>
                <NumberFieldDecrement :aria-label="t('common.actions.decrease')" />
                <NumberFieldInput
                  :aria-describedby="
                    taking && takeMax !== null ? 'voucher-adjustment-max' : undefined
                  "
                />
                <NumberFieldIncrement :aria-label="t('common.actions.increase')" />
              </NumberFieldContent>
            </NumberField>
          </div>
          <p v-if="attempted && amountInvalid" class="text-sm text-destructive">
            {{ t('vouchers.admin.amountInvalid', { max: MAX_ADJUSTMENT }) }}
          </p>
          <p
            v-else-if="taking && takeMax !== null"
            id="voucher-adjustment-max"
            class="text-xs"
            :class="overCap ? 'text-destructive' : 'text-muted-foreground'"
            :role="overCap ? 'status' : undefined"
            data-testid="voucher-adjustment-max"
          >
            {{ t('vouchers.admin.takeAwayMax', { n: takeMax, name: currentName }) }}
          </p>
          <p v-else class="text-xs text-muted-foreground">{{ t('vouchers.admin.amountHint') }}</p>
        </div>

        <div class="space-y-2">
          <Label for="voucher-adjustment-note">{{ t('vouchers.admin.note') }} *</Label>
          <Textarea
            id="voucher-adjustment-note"
            v-model="note"
            :placeholder="t('vouchers.admin.notePlaceholder')"
            maxlength="500"
            rows="2"
            required
            :aria-invalid="attempted && noteMissing ? 'true' : undefined"
            :aria-describedby="attempted && noteMissing ? 'voucher-adjustment-note-error' : undefined"
            data-testid="voucher-adjustment-note"
          />
          <p
            v-if="attempted && noteMissing"
            id="voucher-adjustment-note-error"
            class="text-sm text-destructive"
            data-testid="voucher-adjustment-note-error"
          >
            {{ t('vouchers.admin.noteRequired') }}
          </p>
        </div>

        <p
          v-if="availableAfter !== null"
          class="flex items-center justify-between gap-2 rounded-lg bg-muted px-3.5 py-2.5 text-sm text-muted-foreground"
          data-testid="voucher-adjustment-after"
        >
          {{ t('vouchers.admin.availableAfter') }}
          <span class="text-lg font-bold text-foreground tabular-nums">{{ availableAfter }}</span>
        </p>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter>
        <Button variant="outline" @click="open = false">
          {{ t('common.actions.cancel') }}
        </Button>
        <Button :disabled="saving" data-testid="btn-save-voucher-adjustment" @click="save">
          {{ t('vouchers.admin.save') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
