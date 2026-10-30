<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { CalendarRange, History, QrCode, ScanLine, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Alert, AlertDescription } from '@/components/ui/alert'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  <div class="mx-auto max-w-2xl space-y-6">
    <div class="space-y-1">
      <h1 data-testid="page-heading" class="text-2xl font-bold sm:text-3xl">
        {{ t('vouchers.myTitle') }}
      </h1>
      <p v-if="event" class="text-muted-foreground">{{ event.name }}</p>
    </div>

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

    <div v-else-if="loading" class="space-y-4">
      <Skeleton class="h-48 w-full rounded-xl" />
      <Skeleton class="h-64 w-full rounded-xl" />
    </div>

    <Alert v-else-if="failed" variant="destructive">
      <AlertDescription>{{ t('vouchers.loadFailed') }}</AlertDescription>
    </Alert>

    <template v-else-if="account">
      <Alert v-if="expired" data-testid="my-vouchers-expired">
        <AlertDescription>{{ t('vouchers.expired') }}</AlertDescription>
      </Alert>

      <Card data-testid="my-vouchers-balance">
        <CardHeader class="pb-3">
          <CardTitle class="flex items-center gap-2 text-lg">
            <Ticket class="size-5 shrink-0" />
            {{ t('vouchers.title') }}
          </CardTitle>
          <CardDescription>{{ t('vouchers.howItWorks') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <VoucherBalanceSummary :summary="account.summary" />
          <template v-if="!expired">
            <Button
              size="lg"
              class="w-full"
              :disabled="account.summary.available === 0"
              data-testid="btn-show-voucher-code"
              @click="codeOpen = true"
            >
              <QrCode class="mr-2 size-5" />
              {{ t('vouchers.showCode') }}
            </Button>
            <p v-if="account.summary.available === 0" class="text-sm text-muted-foreground">
              {{ t('vouchers.noneAvailable') }}
            </p>
          </template>
          <Button
            v-if="canRedeemSomewhere && !expired"
            variant="outline"
            class="w-full"
            data-testid="btn-open-redeem"
            @click="router.push({ name: 'voucher-redeem', params: { eventId } })"
          >
            <ScanLine class="mr-2 size-4" />
            {{ t('vouchers.redeem.open') }}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="pb-1">
          <CardTitle class="flex items-center gap-2 text-lg">
            <History class="size-5 shrink-0" />
            {{ t('vouchers.history.title') }}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <VoucherHistory :account="account" />
        </CardContent>
      </Card>
    </template>

    <VoucherCodeDialog
      v-if="eventId && !expired"
      v-model:open="codeOpen"
      :event-id="eventId"
      @redeemed="reloadAccount"
    />
  </div>
</template>
