<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, Info, Loader2, Minus, Plus, ScanLine, Ticket, UserSearch } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
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
  RESPONSIVE_DIALOG_MOBILE_QUERY,
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import type { VoucherRedeemResult } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { initials } from '@/lib/format'
import { type CodeUsedDetails, codeUsedDetails, newRequestId } from '@/lib/vouchers'

/** Who is at the counter, as `POST …/vouchers/check` answered. */
export interface RedeemSubject {
  /** The code they showed; `null` when the redeemer picked them by hand. */
  code: string | null
  userId: string
  name: string | null
  avatarEtag: string | null
  available: number
}

/**
 * The step between "who is this" and "done": how many to take, then the
 * answer. A bottom drawer on phones with one big button.
 *
 * The person sits on top as a chip with what they have, so whoever is at the
 * counter can check name and number at a glance; once redeemed the sheet
 * turns into a big tick with what is left. "Next person" (`next`) closes it
 * and gets the page ready for the next one; "Done" only closes it.
 *
 * One `request_id` per opening, reused by every retry, so a redemption whose
 * answer got lost on a busy network is reported rather than taken twice.
 */
const props = defineProps<{
  eventId: string
  taskId: string
  subject: RedeemSubject | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  redeemed: [result: VoucherRedeemResult]
  /** "Next person": the sheet closes, and the page readies the next redemption. */
  next: []
}>()

const { t, locale } = useI18n()
const { post } = useAuthenticatedClient()

/** The same line the dialog itself switches to a bottom drawer at. */
const isPhone = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)

/** One redemption never takes more than this (the server's limit). */
const MAX_PER_REDEMPTION = 50

/** `undefined` once the field is emptied: reka's number field reports no number then. */
const amount = ref<number | undefined>(1)
/** What is in the field while someone types, before it is committed on blur or Enter. */
const typedAmount = ref<number | null>(null)
const available = ref(0)
const requestId = ref('')
const busy = ref(false)
const result = ref<VoucherRedeemResult | null>(null)
const alreadyUsed = ref<CodeUsedDetails | null>(null)

const name = computed(() => props.subject?.name || '?')
/** Picked by hand: the next one is probably picked the same way. */
const byHand = computed(() => !!props.subject && !props.subject.code)
const avatarUrl = computed(() =>
  props.subject
    ? avatarUrlFor({ id: props.subject.userId, avatar_etag: props.subject.avatarEtag })
    : null,
)
const max = computed(() => Math.max(1, Math.min(available.value, MAX_PER_REDEMPTION)))

/** The number in the field right now, typed or committed; `null` while it is empty. */
const shownAmount = computed(() => {
  const n = typedAmount.value ?? amount.value
  return typeof n === 'number' && Number.isFinite(n) ? n : null
})
/** What will be redeemed: the field clamps to 1…max when it commits. */
const redeemAmount = computed(() =>
  shownAmount.value === null ? null : Math.min(Math.max(1, shownAmount.value), max.value),
)
const overMax = computed(() => shownAmount.value !== null && shownAmount.value > max.value)
/** Nothing left to choose: done, refused, or nothing to take. */
const finished = computed(() => !!result.value || !!alreadyUsed.value || available.value === 0)

// A committed value (blur, Enter, the ± buttons) replaces what was typed.
watch(amount, () => {
  typedAmount.value = null
})

function onAmountInput(event: Event) {
  const text = (event.target as HTMLInputElement | null)?.value.trim() ?? ''
  typedAmount.value = text === '' ? Number.NaN : Number.parseInt(text, 10)
}

/**
 * "Next person" was pressed. The page is told once the sheet has gone and
 * would hand focus back, so what it focuses next (the picker, the code field)
 * is not taken away again by the closing sheet.
 */
let nextPending = false

watch(open, (isOpen) => {
  if (!isOpen) return
  nextPending = false
  amount.value = 1
  typedAmount.value = null
  available.value = props.subject?.available ?? 0
  requestId.value = newRequestId()
  result.value = null
  alreadyUsed.value = null
})

function next() {
  nextPending = true
  open.value = false
}

function onCloseAutoFocus(event: Event) {
  if (!nextPending) return
  nextPending = false
  event.preventDefault()
  emit('next')
}

function timeOf(d: Date | null): string {
  return d ? d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' }) : ''
}

async function redeem() {
  const s = props.subject
  const n = amount.value
  // An emptied field is no amount at all; never send a redemption without one.
  if (!s || busy.value || result.value || n === undefined || !Number.isInteger(n)) return
  busy.value = true
  try {
    const res = await post<{ data: VoucherRedeemResult }>({
      url: `/events/${props.eventId}/vouchers/redeem`,
      body: {
        task_id: props.taskId,
        ...(s.code ? { code: s.code } : { user_id: s.userId }),
        amount: n,
        request_id: requestId.value,
      },
    })
    result.value = res.data
    available.value = res.data.available
    emit('redeemed', res.data)
  } catch (error) {
    const used = codeUsedDetails(error)
    if (used) {
      alreadyUsed.value = used
      return
    }
    const problem = toastApiError(error)
    // Nothing was taken; offer what there is.
    if (problem.code === 'voucher.insufficient') {
      const response = (error as { response?: { data?: { available?: unknown } } }).response
      const left = response?.data?.available
      if (typeof left === 'number') {
        available.value = left
        amount.value = Math.max(1, Math.min(n, left))
      }
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent
      dialog-class="sm:max-w-[420px] sm:rounded-[20px]"
      keep-keyboard-closed
      data-testid="voucher-redeem-confirm"
      @close-auto-focus="onCloseAutoFocus"
    >
      <!-- Done: a big tick, who it was for and what is left -->
      <ResponsiveDialogBody
        v-if="result"
        class="flex flex-col items-center gap-3.5 pb-2 text-center"
        :class="isPhone ? 'pt-4' : 'pt-7'"
      >
        <span
          class="flex shrink-0 items-center justify-center rounded-full bg-primary/18 text-primary"
          :class="isPhone ? 'size-18' : 'size-16'"
          aria-hidden="true"
        >
          <Check :class="isPhone ? 'size-9' : 'size-8'" :stroke-width="2.5" />
        </span>
        <div role="status" data-testid="voucher-redeem-success">
          <ResponsiveDialogTitle class="font-bold" :class="isPhone ? 'text-2xl' : 'text-[22px]'">
            {{ t('vouchers.redeem.done', { n: -result.entry.amount }, -result.entry.amount) }}
          </ResponsiveDialogTitle>
          <ResponsiveDialogDescription
            class="mt-1 text-muted-foreground"
            :class="isPhone ? 'text-base' : 'text-[15px]'"
          >
            {{ t('vouchers.redeem.doneFor', { name: result.name || name }) }}
          </ResponsiveDialogDescription>
        </div>
        <span
          class="flex items-center gap-1.5 rounded-full bg-secondary font-bold text-secondary-foreground tabular-nums"
          :class="isPhone ? 'px-3 py-1 text-[15px]' : 'px-[11px] py-1 text-sm'"
          data-testid="voucher-redeem-left"
        >
          <Ticket class="size-4 shrink-0" aria-hidden="true" />
          {{ t('vouchers.redeem.left', { n: result.available }, result.available) }}
        </span>
      </ResponsiveDialogBody>

      <template v-else>
        <ResponsiveDialogHeader>
          <ResponsiveDialogTitle class="text-xl font-bold">
            {{ t('vouchers.redeem.title') }}
          </ResponsiveDialogTitle>
          <ResponsiveDialogDescription class="sr-only">
            {{ t('vouchers.redeem.hasAvailable', { name, n: available }, available) }}
          </ResponsiveDialogDescription>
        </ResponsiveDialogHeader>

        <ResponsiveDialogBody class="space-y-[18px] pb-4">
          <!-- Who: the name and what they have, to check at a glance -->
          <div
            v-if="subject"
            class="flex items-center rounded-2xl border bg-card"
            :class="isPhone ? 'gap-3.5 p-3.5' : 'gap-3 px-3.5 py-3'"
            data-testid="voucher-redeem-person"
          >
            <Avatar class="shrink-0" :class="isPhone ? 'size-12' : 'size-11'">
              <AvatarImage v-if="avatarUrl" :src="avatarUrl" />
              <AvatarFallback
                class="bg-accent font-bold text-accent-foreground"
                :class="isPhone ? 'text-base' : 'text-[15px]'"
              >
                {{ initials(name) }}
              </AvatarFallback>
            </Avatar>
            <!-- Two lines rather than "Vroni Hartm…": the name is what gets checked -->
            <span
              class="line-clamp-2 min-w-0 flex-1 leading-tight font-bold break-words"
              :class="isPhone ? 'text-lg' : 'text-[17px]'"
            >
              {{ name }}
            </span>
            <span
              class="flex shrink-0 items-center gap-1.5 rounded-full font-bold tabular-nums"
              :class="[
                available > 0
                  ? 'bg-hero-chip text-hero-chip-foreground'
                  : 'bg-secondary text-secondary-foreground',
                isPhone ? 'px-3 py-1 text-[15px]' : 'px-[11px] py-1 text-sm',
              ]"
              data-testid="voucher-redeem-available"
            >
              <Ticket class="size-4 shrink-0" aria-hidden="true" />
              {{ t('vouchers.redeem.availableChip', { n: available }) }}
            </span>
          </div>

          <!-- The code had been used before: say where, not just "error" -->
          <div
            v-if="alreadyUsed"
            class="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
            role="status"
            data-testid="voucher-redeem-already"
          >
            <Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{
              t(
                'vouchers.redeem.alreadyRedeemed',
                {
                  n: alreadyUsed.amount ?? 0,
                  place: alreadyUsed.taskName ?? '?',
                  time: timeOf(alreadyUsed.usedAt),
                },
                alreadyUsed.amount ?? 0,
              )
            }}
          </div>

          <p v-else-if="available === 0" class="text-sm text-muted-foreground">
            {{ t('vouchers.redeem.noneLeft', { name }) }}
          </p>

          <NumberField
            v-else
            id="voucher-redeem-amount"
            v-model="amount"
            :min="1"
            :max="max"
            :disabled="busy"
            class="gap-2"
            data-testid="voucher-redeem-amount"
          >
            <Label
              for="voucher-redeem-amount"
              class="font-bold"
              :class="isPhone ? 'text-[15px]' : 'text-sm'"
            >
              {{ t('vouchers.redeem.amount') }}
            </Label>
            <NumberFieldContent
              class="flex items-center border bg-card focus-within:ring-[3px] focus-within:ring-ring/50"
              :class="isPhone ? 'rounded-2xl' : 'rounded-[14px]'"
            >
              <NumberFieldDecrement
                class="static flex shrink-0 translate-y-0 items-center justify-center p-0 disabled:opacity-30"
                :class="isPhone ? 'size-16' : 'size-14'"
                :aria-label="t('common.actions.decrease')"
                data-testid="btn-voucher-amount-decrease"
              >
                <Minus class="size-6" />
              </NumberFieldDecrement>
              <NumberFieldInput
                class="min-w-0 flex-1 rounded-none border-0 bg-transparent px-0 font-bold tabular-nums shadow-none focus-visible:ring-0"
                :class="isPhone ? 'h-16 text-[30px]' : 'h-14 text-[26px]'"
                @input="onAmountInput"
                @blur="typedAmount = null"
                @keydown.enter="typedAmount = null"
              />
              <NumberFieldIncrement
                class="static flex shrink-0 translate-y-0 items-center justify-center p-0 disabled:opacity-30"
                :class="isPhone ? 'size-16' : 'size-14'"
                :aria-label="t('common.actions.increase')"
                data-testid="btn-voucher-amount-increase"
              >
                <Plus class="size-6" />
              </NumberFieldIncrement>
            </NumberFieldContent>
            <p
              v-if="overMax"
              class="text-sm text-muted-foreground"
              data-testid="voucher-redeem-max"
            >
              {{ t('vouchers.redeem.atMost', { n: max }) }}
            </p>
          </NumberField>
        </ResponsiveDialogBody>
      </template>

      <!--
        A phone stacks the buttons with the main one on top (the footer
        reverses them); a desktop dialog puts them in a row, the main one last.
      -->
      <ResponsiveDialogFooter :class="isPhone ? 'border-t-0' : result ? 'justify-center' : ''">
        <template v-if="finished">
          <Button
            :variant="isPhone ? 'ghost' : 'outline'"
            :class="isPhone ? 'h-12 text-base font-semibold' : 'h-11 px-[18px] font-semibold'"
            data-testid="btn-voucher-done"
            @click="open = false"
          >
            {{ t('vouchers.redeem.finish') }}
          </Button>
          <Button
            :class="
              isPhone ? 'h-[54px] rounded-[14px] text-[17px] font-bold' : 'h-11 px-5 font-bold'
            "
            data-testid="btn-voucher-next"
            @click="next"
          >
            <UserSearch v-if="byHand" class="size-5" aria-hidden="true" />
            <ScanLine v-else class="size-5" aria-hidden="true" />
            {{ t('vouchers.redeem.next') }}
          </Button>
        </template>
        <template v-else>
          <Button
            :variant="isPhone ? 'ghost' : 'outline'"
            :class="isPhone ? 'h-12 text-base font-semibold' : 'h-11 px-[18px] font-semibold'"
            :disabled="busy"
            @click="open = false"
          >
            {{ t('common.actions.cancel') }}
          </Button>
          <Button
            :class="
              isPhone ? 'h-[54px] rounded-[14px] text-[17px] font-bold' : 'h-11 px-5 font-bold'
            "
            :disabled="busy || !subject || redeemAmount === null"
            data-testid="btn-voucher-redeem"
            @click="redeem"
          >
            <Loader2 v-if="busy" class="size-4 animate-spin" aria-hidden="true" />
            {{
              redeemAmount === null
                ? t('vouchers.redeem.confirmNoAmount')
                : t('vouchers.redeem.confirm', { n: redeemAmount }, redeemAmount)
            }}
          </Button>
        </template>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
