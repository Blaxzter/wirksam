<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { AlertTriangle, Plus, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import VoucherAdjustmentDialog from '@/components/events/VoucherAdjustmentDialog.vue'
import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'
import VoucherHistory from '@/components/vouchers/VoucherHistory.vue'

import type {
  EventMemberRead,
  VoucherAccount,
  VoucherBalance,
  VoucherEntryRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * The organisers' overview of everyone's vouchers, modelled on `EventHours`:
 * a table on desktop, cards on phones. Most available first, so a person in
 * charge handing out more than their task earns shows up at the top. A row
 * opens that person's history, where corrections can be changed.
 */
const props = defineProps<{
  eventId: string
  members: EventMemberRead[]
}>()

const { t } = useI18n()
const { get, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const balances = ref<VoucherBalance[]>([])

const displayName = (b: Pick<VoucherBalance, 'name' | 'email'>) => b.name ?? b.email ?? '?'

/** Corrections with their sign, so `+5` and `−4` read as what they did. */
const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`)

/** People with nothing to their name stay in the members card; here they are noise. */
const rows = computed(() =>
  balances.value.filter((b) => b.earned > 0 || b.upcoming > 0 || b.redeemed > 0 || b.adjusted !== 0),
)
const anyNegative = computed(() => rows.value.some((b) => b.balance < 0))

async function load() {
  try {
    const res = await get<{ data: VoucherBalance[] }>({
      url: `/events/${props.eventId}/vouchers/people`,
    })
    balances.value = res.data
  } catch (error) {
    toastApiError(error)
  }
}

watch(() => props.eventId, load, { immediate: true })

// --- One person's vouchers ---

const detailOpen = ref(false)
const detail = ref<VoucherAccount | null>(null)

async function loadDetail(userId: string) {
  try {
    const res = await get<{ data: VoucherAccount }>({
      url: `/events/${props.eventId}/vouchers/people/${userId}`,
    })
    detail.value = res.data
  } catch (error) {
    toastApiError(error)
  }
}

async function openDetail(row: VoucherBalance) {
  detail.value = null
  detailOpen.value = true
  await loadDetail(row.user_id)
}

// --- Corrections ---

const formOpen = ref(false)
const formUserId = ref<string | null>(null)
const formUserName = ref<string | null>(null)
const formEntry = ref<VoucherEntryRead | null>(null)

function addCorrection(person: VoucherBalance | null = null) {
  formUserId.value = person?.user_id ?? null
  formUserName.value = person ? displayName(person) : null
  formEntry.value = null
  formOpen.value = true
}

function editCorrection(entry: VoucherEntryRead) {
  formUserId.value = detail.value?.summary.user_id ?? null
  formUserName.value = detail.value ? displayName(detail.value.summary) : null
  formEntry.value = entry
  formOpen.value = true
}

async function deleteCorrection(entry: VoucherEntryRead) {
  const confirmed = await confirmDestructive({
    title: t('vouchers.admin.deleteConfirm'),
    text: t('vouchers.admin.deleteHint'),
    confirmText: t('vouchers.admin.deleteCorrection'),
  })
  if (!confirmed) return
  try {
    await del({ url: `/events/${props.eventId}/vouchers/adjustments/${entry.id}` })
    toast.success(t('vouchers.admin.deleted'))
    await afterChange()
  } catch (error) {
    toastApiError(error)
  }
}

async function afterChange() {
  await load()
  if (detailOpen.value && detail.value) await loadDetail(detail.value.summary.user_id)
}
</script>

<template>
  <Card data-testid="section-event-vouchers">
    <CardHeader>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="space-y-1">
          <CardTitle class="flex items-center gap-2">
            <Ticket class="size-5 shrink-0" />
            {{ t('vouchers.admin.title') }}
          </CardTitle>
          <CardDescription>{{ t('vouchers.admin.subtitle') }}</CardDescription>
        </div>
        <Button size="sm" data-testid="btn-add-voucher-correction" @click="addCorrection()">
          <Plus class="mr-1.5 size-4" />
          {{ t('vouchers.admin.addCorrection') }}
        </Button>
      </div>
    </CardHeader>

    <CardContent class="space-y-3">
      <p v-if="rows.length === 0" class="text-sm text-muted-foreground">
        {{ t('vouchers.admin.empty') }}
      </p>

      <template v-else>
        <!-- Desktop: a table -->
        <Table class="hidden sm:table">
          <TableHeader>
            <TableRow>
              <TableHead>{{ t('vouchers.admin.person') }}</TableHead>
              <TableHead class="text-right">{{ t('vouchers.admin.colAvailable') }}</TableHead>
              <TableHead class="text-right">{{ t('vouchers.admin.colBalance') }}</TableHead>
              <TableHead class="text-right">{{ t('vouchers.admin.colEarned') }}</TableHead>
              <TableHead class="text-right">{{ t('vouchers.admin.colUsed') }}</TableHead>
              <TableHead class="text-right">{{ t('vouchers.adjusted') }}</TableHead>
              <TableHead class="text-right">{{ t('vouchers.admin.colUpcoming') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow
              v-for="row in rows"
              :key="row.user_id"
              class="cursor-pointer"
              data-testid="event-vouchers-row"
              tabindex="0"
              :aria-label="t('vouchers.admin.openDetails', { name: displayName(row) })"
              @click="openDetail(row)"
              @keydown.enter="openDetail(row)"
            >
              <TableCell>
                <p class="font-medium">{{ displayName(row) }}</p>
                <p v-if="!row.role" class="text-xs text-muted-foreground">
                  {{ t('vouchers.admin.left') }}
                </p>
              </TableCell>
              <TableCell class="text-right font-semibold tabular-nums">
                {{ row.available }}
              </TableCell>
              <TableCell
                class="text-right tabular-nums"
                :class="row.balance < 0 ? 'font-semibold text-destructive' : ''"
              >
                {{ row.balance }}
              </TableCell>
              <TableCell class="text-right tabular-nums">{{ row.earned }}</TableCell>
              <TableCell class="text-right tabular-nums">{{ row.redeemed }}</TableCell>
              <TableCell class="text-right tabular-nums" data-testid="event-vouchers-adjusted">
                {{ signed(row.adjusted) }}
              </TableCell>
              <TableCell class="text-right tabular-nums text-muted-foreground">
                {{ row.upcoming }}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>

        <!-- Phone: one card per person -->
        <ul class="space-y-2 sm:hidden">
          <li v-for="row in rows" :key="row.user_id">
            <button
              type="button"
              class="w-full rounded-md border p-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="event-vouchers-card"
              :aria-label="t('vouchers.admin.openDetails', { name: displayName(row) })"
              @click="openDetail(row)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="truncate font-medium">{{ displayName(row) }}</p>
                  <p v-if="!row.role" class="text-xs text-muted-foreground">
                    {{ t('vouchers.admin.left') }}
                  </p>
                </div>
                <div class="shrink-0 text-right">
                  <p class="text-xl leading-none font-bold tabular-nums">{{ row.available }}</p>
                  <p class="text-xs text-muted-foreground">{{ t('vouchers.admin.colAvailable') }}</p>
                </div>
              </div>
              <dl class="mt-2 grid grid-cols-3 gap-x-2 gap-y-1.5 text-xs">
                <div>
                  <dt class="text-muted-foreground">{{ t('vouchers.admin.colBalance') }}</dt>
                  <dd
                    class="tabular-nums"
                    :class="row.balance < 0 ? 'font-semibold text-destructive' : ''"
                  >
                    {{ row.balance }}
                  </dd>
                </div>
                <div>
                  <dt class="text-muted-foreground">{{ t('vouchers.admin.colEarned') }}</dt>
                  <dd class="tabular-nums">{{ row.earned }}</dd>
                </div>
                <div>
                  <dt class="text-muted-foreground">{{ t('vouchers.admin.colUsed') }}</dt>
                  <dd class="tabular-nums">{{ row.redeemed }}</dd>
                </div>
                <div>
                  <dt class="text-muted-foreground">{{ t('vouchers.adjusted') }}</dt>
                  <dd class="tabular-nums">{{ signed(row.adjusted) }}</dd>
                </div>
                <div>
                  <dt class="text-muted-foreground">{{ t('vouchers.admin.colUpcoming') }}</dt>
                  <dd class="tabular-nums">{{ row.upcoming }}</dd>
                </div>
              </dl>
            </button>
          </li>
        </ul>

        <p
          v-if="anyNegative"
          class="flex items-start gap-1.5 text-xs text-muted-foreground"
          data-testid="event-vouchers-negative"
        >
          <AlertTriangle class="mt-0.5 size-3.5 shrink-0 text-destructive" />
          {{ t('vouchers.admin.balanceNegative') }}
        </p>
      </template>

      <p class="text-xs text-muted-foreground">{{ t('vouchers.admin.afterEventHint') }}</p>
    </CardContent>
  </Card>

  <ResponsiveDialog v-model:open="detailOpen">
    <ResponsiveDialogContent dialog-class="sm:max-w-lg" data-testid="event-vouchers-detail">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>
          {{ t('vouchers.admin.detailTitle', { name: detail ? displayName(detail.summary) : '' }) }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="sr-only">
          {{ t('vouchers.admin.detailDescription', { name: detail ? displayName(detail.summary) : '' }) }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-4 pb-2">
        <div v-if="!detail" class="py-6 text-center text-sm text-muted-foreground">
          {{ t('common.states.loading') }}
        </div>
        <template v-else>
          <VoucherBalanceSummary :summary="detail.summary" compact other />
          <p
            v-if="detail.summary.balance < 0"
            class="flex items-start gap-1.5 text-xs text-destructive"
          >
            <AlertTriangle class="mt-0.5 size-3.5 shrink-0" />
            {{ t('vouchers.admin.balanceNegative') }}
          </p>
          <VoucherHistory
            :account="detail"
            can-edit
            @edit="editCorrection"
            @delete="deleteCorrection"
          />
        </template>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter v-if="detail" class="sm:justify-start">
        <Button size="sm" @click="addCorrection(detail.summary)">
          <Plus class="mr-1.5 size-4" />
          {{ t('vouchers.admin.addCorrection') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>

  <VoucherAdjustmentDialog
    v-model:open="formOpen"
    :event-id="eventId"
    :members="members"
    :user-id="formUserId"
    :user-name="formUserName"
    :entry="formEntry"
    :balances="balances"
    @saved="afterChange"
  />
</template>
