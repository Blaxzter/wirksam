<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { CalendarRange, QrCode, ScanLine, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Alert, AlertDescription } from '@/components/ui/alert'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'
import VoucherCodeDialog from '@/components/vouchers/VoucherCodeDialog.vue'
import VoucherHistory from '@/components/vouchers/VoucherHistory.vue'

import type { EventRead, VoucherAccount, VoucherPointRead } from '@/client/types.gen'

/**
 * "My vouchers": what the volunteer can use now, where it came from, and the
 * button that shows their code.
 *
 * Exempt from the expired-event guard, so "did I get mine?" still has an
 * answer the morning after. Once the event is over the page only reads: no
 * code can be shown any more.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()

const eventId = computed(
  () => (route.params.eventId as string | undefined) || authStore.selectedEventId || null,
)

const event = ref<EventRead | null>(null)
const account = ref<VoucherAccount | null>(null)
const points = ref<VoucherPointRead[]>([])
const loading = ref(false)
const failed = ref(false)
const codeOpen = ref(false)

const expired = computed(() => !!event.value?.is_expired)
const canRedeemSomewhere = computed(() => points.value.some((p) => p.can_redeem))

async function loadAccount(id: string) {
  const res = await get<{ data: VoucherAccount }>({ url: `/events/${id}/vouchers/me` })
  if (eventId.value === id) account.value = res.data
}

async function load() {
  const id = eventId.value
  event.value = null
  account.value = null
  points.value = []
  failed.value = false
  if (!id) return
  loading.value = true
  try {
    const [eventRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${id}` }),
      loadAccount(id),
    ])
    if (eventId.value !== id) return
    event.value = eventRes.data
  } catch {
    if (eventId.value === id) failed.value = true
  } finally {
    loading.value = false
  }
  // Only decides whether to offer the redeem page; a failure costs nothing.
  try {
    const res = await get<{ data: VoucherPointRead[] }>({ url: `/events/${id}/vouchers/points` })
    if (eventId.value === id) points.value = res.data
  } catch {
    points.value = []
  }
}

async function reloadAccount() {
  if (!eventId.value) return
  try {
    await loadAccount(eventId.value)
  } catch {
    // Keep what is shown; the next visit reads it again.
  }
}

watch(eventId, load, { immediate: true })
</script>

<template>
  <!--
    One column on a phone; from about 56rem of room the numbers sit on the
    left at most 26rem wide and the history takes the rest.
  -->
  <div class="@container mx-auto flex max-w-[65rem] flex-col gap-4 sm:gap-6">
    <header>
      <h1
        data-testid="page-heading"
        class="text-[1.625rem] leading-tight font-bold tracking-tight sm:text-[2rem]"
      >
        {{ t('vouchers.myTitle') }}
      </h1>
      <p v-if="event" class="mt-0.5 text-sm text-muted-foreground sm:mt-1 sm:text-[15px]">
        {{ event.name }}
      </p>
    </header>

    <!-- No event at all: the way out is the picker -->
    <Card v-if="!eventId" data-testid="my-vouchers-no-event">
      <CardContent class="flex flex-col items-start gap-3 pt-6">
        <p class="text-muted-foreground">{{ t('vouchers.noEvent') }}</p>
        <Button
          variant="outline"
          @click="router.push({ name: 'select-event', query: { mode: 'switch' } })"
        >
          <CalendarRange class="mr-2 size-4" />
          {{ t('vouchers.pickEvent') }}
        </Button>
      </CardContent>
    </Card>

    <div
      v-else-if="loading"
      class="grid gap-4 sm:gap-6 @4xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]"
    >
      <Skeleton class="h-80 w-full rounded-[20px] sm:rounded-[22px]" />
      <Skeleton class="h-64 w-full rounded-[20px] sm:rounded-[22px]" />
    </div>

    <Alert v-else-if="failed" variant="destructive">
      <AlertDescription>{{ t('vouchers.loadFailed') }}</AlertDescription>
    </Alert>

    <template v-else-if="account">
      <Alert v-if="expired" data-testid="my-vouchers-expired">
        <AlertDescription>{{ t('vouchers.expired') }}</AlertDescription>
      </Alert>

      <div class="grid items-start gap-4 sm:gap-6 @4xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <section
          aria-labelledby="my-vouchers-stats"
          data-testid="my-vouchers-balance"
          class="flex min-w-0 flex-col rounded-[20px] border bg-card px-4 pt-[18px] pb-4 text-card-foreground sm:rounded-[22px] sm:p-6"
        >
          <h2
            id="my-vouchers-stats"
            class="flex items-center gap-2 text-[13px] font-semibold text-muted-foreground sm:text-base sm:font-bold sm:text-card-foreground"
          >
            <Ticket class="size-4 shrink-0 sm:size-[18px]" aria-hidden="true" />
            {{ t('vouchers.yours') }}
          </h2>
          <VoucherBalanceSummary class="mt-2.5 sm:mt-3.5" :summary="account.summary" />

          <template v-if="!expired">
            <Button
              class="mt-4 h-[50px] w-full rounded-xl text-base font-bold sm:mt-[18px] sm:h-12 sm:text-[15px]"
              :disabled="account.summary.available === 0"
              data-testid="btn-show-voucher-code"
              @click="codeOpen = true"
            >
              <QrCode class="size-[18px]" aria-hidden="true" />
              {{ t('vouchers.showCode') }}
            </Button>
            <p v-if="account.summary.available === 0" class="mt-2 text-sm text-muted-foreground">
              {{ t('vouchers.noneAvailable') }}
            </p>
            <Button
              v-if="canRedeemSomewhere"
              variant="outline"
              class="mt-2 h-11 w-full rounded-xl font-semibold"
              data-testid="btn-open-redeem"
              @click="router.push({ name: 'voucher-redeem', params: { eventId } })"
            >
              <ScanLine class="size-4" aria-hidden="true" />
              {{ t('vouchers.redeem.open') }}
            </Button>
          </template>

          <p class="mt-3 text-[13px] text-muted-foreground sm:mt-3.5">
            {{ t('vouchers.howItWorks') }}
          </p>
        </section>

        <section
          aria-labelledby="my-vouchers-history"
          class="min-w-0 rounded-[20px] border bg-card text-card-foreground sm:rounded-[22px]"
        >
          <h2
            id="my-vouchers-history"
            class="px-4 pt-4 pb-1 text-[17px] font-bold sm:px-6 sm:pt-5 sm:pb-1.5 sm:text-lg"
          >
            {{ t('vouchers.history.title') }}
          </h2>
          <VoucherHistory :account="account" with-upcoming class="px-2 pb-2.5 sm:px-4 sm:pb-3.5" />
        </section>
      </div>
    </template>

    <VoucherCodeDialog
      v-if="eventId && !expired"
      v-model:open="codeOpen"
      :event-id="eventId"
      @redeemed="reloadAccount"
    />
  </div>
</template>
