<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Minus, Plus, Scale, TriangleAlert, X } from '@lucide/vue'
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

/**
 * Add or take away vouchers by hand, with a reason. The amount is always typed
 * as a positive number and the direction picked beside it, because a phone's
 * number pad often has no minus key.
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

const personMissing = computed(() => !isEdit.value && !personId.value)
const amountInvalid = computed(
  () =>
    amount.value === undefined ||
    !Number.isInteger(amount.value) ||
    amount.value < 1 ||
    amount.value > MAX_ADJUSTMENT,
)
const noteMissing = computed(() => note.value.trim().length === 0)
const valid = computed(() => !personMissing.value && !amountInvalid.value && !noteMissing.value)

/** The chosen person's balance now, from the overview. */
const current = computed(() => {
  const id = props.entry ? (props.userId ?? null) : personId.value
  return id ? (props.balances?.find((b) => b.user_id === id) ?? null) : null
})
const currentName = computed(() =>
  current.value ? (current.value.name ?? current.value.email ?? '?') : '',
)
/** What their balance would be after saving; an edit replaces its old amount. */
const balanceAfter = computed(() => {
  if (!current.value || amountInvalid.value) return null
  const n = amount.value as number
  const signed = direction.value === 'take' ? -n : n
  return current.value.balance - (props.entry?.amount ?? 0) + signed
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
        <p v-else-if="userName" class="text-sm">
          <span class="text-muted-foreground">{{ t('vouchers.admin.person') }}:</span>
          {{ userName }}
        </p>
        <p
          v-if="showPicker && attempted && personMissing"
          class="-mt-2 text-sm text-destructive"
          data-testid="voucher-adjustment-person-error"
        >
          {{ t('vouchers.admin.personRequired') }}
        </p>
        <p
          v-if="current"
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
              :max="MAX_ADJUSTMENT"
              class="w-32"
              data-testid="voucher-adjustment-amount"
            >
              <NumberFieldContent>
                <NumberFieldDecrement :aria-label="t('common.actions.decrease')" />
                <NumberFieldInput />
                <NumberFieldIncrement :aria-label="t('common.actions.increase')" />
              </NumberFieldContent>
            </NumberField>
          </div>
          <p v-if="attempted && amountInvalid" class="text-sm text-destructive">
            {{ t('vouchers.admin.amountInvalid', { max: MAX_ADJUSTMENT }) }}
          </p>
          <p v-else class="text-xs text-muted-foreground">{{ t('vouchers.admin.amountHint') }}</p>
          <p
            v-if="balanceAfter !== null && balanceAfter < 0"
            class="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-50 p-2.5 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
            role="status"
            data-testid="voucher-adjustment-below-zero"
          >
            <TriangleAlert class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            {{ t('vouchers.admin.belowZero', { name: currentName, n: balanceAfter }) }}
          </p>
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
