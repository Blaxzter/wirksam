<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ChevronRight, Plus, Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'
import { useDialog } from '@/composables/useDialog'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Input from '@/components/ui/input/Input.vue'
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
import { initials } from '@/lib/format'
import { signedVoucherAmount } from '@/lib/vouchers'

/**
 * "Who has how many vouchers", the organisers' overview in the event settings'
 * Vouchers tab, under the voucher rules: a table on desktop, cards on phones,
 * with a search by name. Most available first, so a person in charge handing
 * out more than their task earns shows up at the top. A row opens that
 * person's history, where corrections can be changed.
 *
 * "Available" is the one number: earned vouchers stay earned and corrections
 * can't take away more than is left, so it never goes below zero.
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
const signed = signedVoucherAmount

const avatarSrc = (b: VoucherBalance) =>
  avatarUrlFor({ id: b.user_id, avatar_etag: b.avatar_etag }) ?? undefined

/** People with nothing to their name stay in the members card; here they are noise. */
const rows = computed(() =>
  balances.value.filter(
    (b) => b.earned > 0 || b.upcoming > 0 || b.redeemed > 0 || b.adjusted !== 0,
  ),
)

/** "8 people · 36 vouchers used · 206 still to come", over everyone, not just the matches. */
function summaryLine(usedKey: string) {
  const used = rows.value.reduce((sum, b) => sum + b.redeemed, 0)
  const coming = rows.value.reduce((sum, b) => sum + b.upcoming, 0)
  return [
    t('vouchers.admin.summaryPeople', { n: rows.value.length }, rows.value.length),
    t(usedKey, { n: used }, used),
    t('vouchers.admin.summaryUpcoming', { n: coming }, coming),
  ].join(' · ')
}
const summary = computed(() => summaryLine('vouchers.admin.summaryUsed'))
const summaryShort = computed(() => summaryLine('vouchers.admin.summaryUsedShort'))

const search = ref('')
const shownRows = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return rows.value
  return rows.value.filter((b) =>
    [b.name, b.email].some((field) => field?.toLowerCase().includes(query)),
  )
})

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
  <!--
    A card on a desktop; on a phone the people are cards themselves, so the
    section around them drops its own frame and sits on the page.
  -->
  <Card
    class="gap-4 rounded-[22px] max-sm:gap-3 max-sm:border-0 max-sm:bg-transparent max-sm:py-0 max-sm:shadow-none"
    data-testid="section-event-vouchers"
  >
    <CardHeader class="max-sm:px-0">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div class="space-y-1 max-sm:space-y-0.5">
          <CardTitle class="text-[17px] leading-snug font-bold sm:text-lg">
            {{ t('vouchers.admin.overviewTitle') }}
          </CardTitle>
          <!-- A phone's line is shorter: "8 people · 36 used · 206 still to come" -->
          <CardDescription class="max-sm:text-[13px]">
            <span class="sm:hidden" data-testid="event-vouchers-summary-short">
              {{ summaryShort }}
            </span>
            <span class="max-sm:hidden" data-testid="event-vouchers-summary">{{ summary }}</span>
          </CardDescription>
        </div>
        <div class="flex w-full gap-2 sm:w-auto">
          <div v-if="rows.length > 0" class="relative min-w-0 flex-1 sm:w-60 sm:flex-none">
            <Search
              class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              v-model="search"
              type="search"
              :aria-label="t('vouchers.admin.search')"
              :placeholder="t('vouchers.admin.search')"
              class="h-11 pl-9 sm:h-9"
              data-testid="event-vouchers-search"
            />
          </div>
          <Button
            class="h-11 shrink-0 sm:h-9"
            :aria-label="t('vouchers.admin.addCorrection')"
            data-testid="btn-add-voucher-correction"
            @click="addCorrection()"
          >
            <Plus class="size-4" aria-hidden="true" />
            {{ t('vouchers.admin.correction') }}
          </Button>
        </div>
      </div>
    </CardHeader>

    <CardContent class="space-y-3 max-sm:px-0">
      <p v-if="rows.length === 0" class="text-sm text-muted-foreground">
        {{ t('vouchers.admin.empty') }}
      </p>

      <p
        v-else-if="shownRows.length === 0"
        class="py-4 text-center text-sm text-muted-foreground"
        data-testid="event-vouchers-no-match"
      >
        {{ t('vouchers.admin.noMatch', { q: search.trim() }) }}
      </p>

      <template v-else>
        <!-- Desktop: a table -->
        <div class="hidden overflow-hidden rounded-xl border sm:block">
          <Table>
            <TableHeader class="bg-muted/60">
              <TableRow>
                <TableHead class="pl-4">{{ t('vouchers.admin.person') }}</TableHead>
                <TableHead class="text-right font-bold text-foreground">
                  {{ t('vouchers.admin.colAvailable') }}
                </TableHead>
                <TableHead class="text-right">{{ t('vouchers.admin.colEarned') }}</TableHead>
                <TableHead class="text-right">{{ t('vouchers.admin.colUsed') }}</TableHead>
                <TableHead class="text-right">{{ t('vouchers.admin.correction') }}</TableHead>
                <TableHead class="text-right">{{ t('vouchers.admin.colUpcoming') }}</TableHead>
                <TableHead class="w-12">
                  <span class="sr-only">{{ t('vouchers.admin.open') }}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="row in shownRows"
                :key="row.user_id"
                class="cursor-pointer"
                data-testid="event-vouchers-row"
                @click="openDetail(row)"
              >
                <TableCell class="pl-4">
                  <div class="flex items-center gap-2.5">
                    <Avatar class="size-8">
                      <AvatarImage v-if="avatarSrc(row)" :src="avatarSrc(row)!" />
                      <AvatarFallback class="text-xs font-semibold">
                        {{ initials(displayName(row)) }}
                      </AvatarFallback>
                    </Avatar>
                    <div class="min-w-0">
                      <p class="truncate font-medium">{{ displayName(row) }}</p>
                      <p v-if="!row.role" class="text-xs text-muted-foreground">
                        {{ t('vouchers.admin.left') }}
                      </p>
                    </div>
                  </div>
                </TableCell>
                <TableCell
                  class="text-right text-base font-bold tabular-nums"
                  data-testid="event-vouchers-available"
                >
                  {{ row.available }}
                </TableCell>
                <TableCell class="text-right tabular-nums">{{ row.earned }}</TableCell>
                <TableCell class="text-right tabular-nums">{{ row.redeemed }}</TableCell>
                <TableCell
                  class="text-right tabular-nums"
                  :class="row.adjusted !== 0 ? 'text-warning' : 'text-muted-foreground'"
                  data-testid="event-vouchers-adjusted"
                >
                  {{ signed(row.adjusted) }}
                </TableCell>
                <TableCell class="text-right tabular-nums text-muted-foreground">
                  {{ row.upcoming }}
                </TableCell>
                <TableCell class="py-1 pr-2 text-center">
                  <Button
                    variant="ghost"
                    size="icon"
                    class="text-muted-foreground"
                    :aria-label="t('vouchers.admin.openDetails', { name: displayName(row) })"
                    data-testid="event-vouchers-open"
                    @click.stop="openDetail(row)"
                  >
                    <ChevronRight class="size-4" aria-hidden="true" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <!-- Phone: one card per person -->
        <ul class="space-y-2.5 sm:hidden">
          <li v-for="row in shownRows" :key="row.user_id">
            <button
              type="button"
              class="w-full rounded-2xl border bg-card px-3.5 pt-3 pb-3.5 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="event-vouchers-card"
              :aria-label="t('vouchers.admin.openDetails', { name: displayName(row) })"
              @click="openDetail(row)"
            >
              <div class="flex items-center gap-2.5">
                <Avatar class="size-9">
                  <AvatarImage v-if="avatarSrc(row)" :src="avatarSrc(row)!" />
                  <AvatarFallback class="text-xs font-semibold">
                    {{ initials(displayName(row)) }}
                  </AvatarFallback>
                </Avatar>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-base font-semibold">{{ displayName(row) }}</p>
                  <p v-if="!row.role" class="text-xs text-muted-foreground">
                    {{ t('vouchers.admin.left') }}
                  </p>
                </div>
                <div class="shrink-0 text-right">
                  <p class="text-2xl leading-none font-bold tabular-nums">{{ row.available }}</p>
                  <p class="text-[11px] text-muted-foreground">
                    {{ t('vouchers.admin.availableCaption') }}
                  </p>
                </div>
              </div>
              <!--
                The last column gets a little more room, so "Kommen noch" fits on
                one line at phone width; on narrower screens a label may wrap,
                and the values still sit on one line at the bottom.
              -->
              <dl
                class="mt-2.5 grid grid-cols-[repeat(3,minmax(0,1fr))_minmax(0,1.2fr)] divide-x divide-border/70 rounded-xl bg-muted/60 text-xs"
              >
                <div class="flex min-w-0 flex-col justify-between px-1.5 py-1.5">
                  <dt class="text-[11px] leading-tight hyphens-auto text-muted-foreground">
                    {{ t('vouchers.admin.colEarned') }}
                  </dt>
                  <dd class="text-[15px] font-bold tabular-nums">{{ row.earned }}</dd>
                </div>
                <div class="flex min-w-0 flex-col justify-between px-1.5 py-1.5">
                  <dt class="text-[11px] leading-tight hyphens-auto text-muted-foreground">
                    {{ t('vouchers.admin.colUsed') }}
                  </dt>
                  <dd class="text-[15px] font-bold tabular-nums">{{ row.redeemed }}</dd>
                </div>
                <div class="flex min-w-0 flex-col justify-between px-1.5 py-1.5">
                  <dt class="text-[11px] leading-tight hyphens-auto text-muted-foreground">
                    {{ t('vouchers.admin.correction') }}
                  </dt>
                  <dd class="text-[15px] font-bold tabular-nums">{{ signed(row.adjusted) }}</dd>
                </div>
                <div class="flex min-w-0 flex-col justify-between px-1.5 py-1.5">
                  <dt class="text-[11px] leading-tight hyphens-auto text-muted-foreground">
                    {{ t('vouchers.admin.colUpcoming') }}
                  </dt>
                  <dd class="text-[15px] font-bold tabular-nums text-muted-foreground">
                    {{ row.upcoming }}
                  </dd>
                </div>
              </dl>
            </button>
          </li>
        </ul>
      </template>

      <dl
        v-if="rows.length > 0"
        class="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground"
        data-testid="event-vouchers-legend"
      >
        <div class="flex gap-1.5">
          <dt class="shrink-0 font-semibold text-foreground/80">
            {{ t('vouchers.admin.colAvailable') }}
          </dt>
          <dd>{{ t('vouchers.admin.colAvailableHint') }}</dd>
        </div>
        <div class="flex gap-1.5">
          <dt class="shrink-0 font-semibold text-foreground/80">
            {{ t('vouchers.admin.colUpcoming') }}
          </dt>
          <dd>{{ t('vouchers.admin.colUpcomingHint') }}</dd>
        </div>
      </dl>
    </CardContent>
  </Card>

  <ResponsiveDialog v-model:open="detailOpen">
    <ResponsiveDialogContent
      class="bg-card"
      dialog-class="rounded-[20px] sm:max-w-[520px]"
      drawer-class="rounded-t-[22px]"
      data-testid="event-vouchers-detail"
    >
      <ResponsiveDialogHeader class="sm:pt-[26px] sm:pb-[18px] sm:pl-7">
        <div class="flex min-w-0 items-center gap-3">
          <Avatar v-if="detail" class="size-10 shrink-0">
            <AvatarImage v-if="avatarSrc(detail.summary)" :src="avatarSrc(detail.summary)!" />
            <AvatarFallback class="bg-accent text-sm font-bold">
              {{ initials(displayName(detail.summary)) }}
            </AvatarFallback>
          </Avatar>
          <ResponsiveDialogTitle class="min-w-0 text-xl leading-tight font-bold">
            {{
              t('vouchers.admin.detailTitle', { name: detail ? displayName(detail.summary) : '' })
            }}
          </ResponsiveDialogTitle>
        </div>
        <ResponsiveDialogDescription class="sr-only">
          {{
            t('vouchers.admin.detailDescription', {
              name: detail ? displayName(detail.summary) : '',
            })
          }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="flex flex-col gap-[18px] pb-2 sm:px-7">
        <div v-if="!detail" class="py-6 text-center text-sm text-muted-foreground">
          {{ t('common.states.loading') }}
        </div>
        <template v-else>
          <div class="rounded-2xl border bg-card p-4" data-testid="event-vouchers-detail-summary">
            <VoucherBalanceSummary :summary="detail.summary" compact other />
          </div>
          <section aria-labelledby="event-vouchers-detail-history">
            <h3
              id="event-vouchers-detail-history"
              class="mb-1 text-xs font-bold tracking-[0.05em] text-muted-foreground uppercase"
            >
              {{ t('vouchers.history.title') }}
            </h3>
            <VoucherHistory
              :account="detail"
              can-edit
              @edit="editCorrection"
              @delete="deleteCorrection"
            />
          </section>
        </template>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter v-if="detail" class="sm:px-7 sm:pb-6">
        <Button
          class="h-11 rounded-xl px-[18px] font-bold"
          data-testid="btn-person-add-correction"
          @click="addCorrection(detail.summary)"
        >
          <Plus class="size-4" aria-hidden="true" />
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
