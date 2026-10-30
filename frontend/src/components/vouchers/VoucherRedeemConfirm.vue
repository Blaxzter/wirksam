<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { CircleCheck, Info, Loader2 } from '@lucide/vue'
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
 * One `request_id` per opening, reused by every retry, so a redemption whose
 * answer got lost on a busy network is reported rather than taken twice.
 */
const props = defineProps<{
  eventId: string
  taskId: string
  subject: RedeemSubject | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ redeemed: [result: VoucherRedeemResult] }>()

const { t, locale } = useI18n()
const { post } = useAuthenticatedClient()

/** One redemption never takes more than this (the server's limit). */
const MAX_PER_REDEMPTION = 50

const amount = ref(1)
const available = ref(0)
const requestId = ref('')
const busy = ref(false)
const result = ref<VoucherRedeemResult | null>(null)
const alreadyUsed = ref<CodeUsedDetails | null>(null)

const name = computed(() => props.subject?.name || '?')
const max = computed(() => Math.max(1, Math.min(available.value, MAX_PER_REDEMPTION)))

watch(open, (isOpen) => {
  if (!isOpen) return
  amount.value = 1
  available.value = props.subject?.available ?? 0
  requestId.value = newRequestId()
  result.value = null
  alreadyUsed.value = null
})

function timeOf(d: Date | null): string {
  return d ? d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' }) : ''
}

async function redeem() {
  const s = props.subject
  if (!s || busy.value || result.value) return
  busy.value = true
  try {
    const res = await post<{ data: VoucherRedeemResult }>({
      url: `/events/${props.eventId}/vouchers/redeem`,
      body: {
        task_id: props.taskId,
        ...(s.code ? { code: s.code } : { user_id: s.userId }),
        amount: amount.value,
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
        amount.value = Math.max(1, Math.min(amount.value, left))
      }
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-sm" data-testid="voucher-redeem-confirm">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>
          {{ t('vouchers.redeem.confirmTitle', { name }) }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="sr-only">
          {{ t('vouchers.redeem.hasAvailable', { name, n: available }, available) }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-5 pb-4">
        <div v-if="subject" class="flex items-center gap-3">
          <Avatar class="size-12 shrink-0">
            <AvatarImage
              v-if="avatarUrlFor({ id: subject.userId, avatar_etag: subject.avatarEtag })"
              :src="avatarUrlFor({ id: subject.userId, avatar_etag: subject.avatarEtag })!"
            />
            <AvatarFallback>{{ initials(name) }}</AvatarFallback>
          </Avatar>
          <div class="min-w-0">
            <p class="truncate font-semibold">{{ name }}</p>
            <p
              v-if="available > 0 || result"
              class="text-sm text-muted-foreground"
              data-testid="voucher-redeem-available"
            >
              {{ t('vouchers.redeem.hasAvailable', { name, n: available }, available) }}
            </p>
          </div>
        </div>

        <!-- Done -->
        <div
          v-if="result"
          class="flex items-start gap-2 rounded-md border border-green-600/30 bg-green-500/10 p-3 text-sm text-green-800 dark:text-green-300"
          role="status"
          data-testid="voucher-redeem-success"
        >
          <CircleCheck class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {{
            t('vouchers.redeem.success', {
              n: -result.entry.amount,
              name: result.name || name,
              left: result.available,
            })
          }}
        </div>

        <!-- The code had been used before: say where, not just "error" -->
        <div
          v-else-if="alreadyUsed"
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
          data-testid="voucher-redeem-amount"
        >
          <Label for="voucher-redeem-amount">{{ t('vouchers.redeem.amount') }}</Label>
          <NumberFieldContent>
            <NumberFieldDecrement
              class="p-4"
              :aria-label="t('common.actions.decrease')"
              data-testid="btn-voucher-amount-decrease"
            />
            <NumberFieldInput class="h-14 text-2xl font-semibold" />
            <NumberFieldIncrement
              class="p-4"
              :aria-label="t('common.actions.increase')"
              data-testid="btn-voucher-amount-increase"
            />
          </NumberFieldContent>
        </NumberField>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter>
        <template v-if="result || alreadyUsed || available === 0">
          <Button size="lg" class="w-full sm:w-auto" data-testid="btn-voucher-next" @click="open = false">
            {{ t('vouchers.redeem.next') }}
          </Button>
        </template>
        <template v-else>
          <Button variant="outline" :disabled="busy" @click="open = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button
            size="lg"
            class="w-full sm:w-auto"
            :disabled="busy || !subject"
            data-testid="btn-voucher-redeem"
            @click="redeem"
          >
            <Loader2 v-if="busy" class="mr-2 size-4 animate-spin" aria-hidden="true" />
            {{ t('vouchers.redeem.confirm', { n: amount }, amount) }}
          </Button>
        </template>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
