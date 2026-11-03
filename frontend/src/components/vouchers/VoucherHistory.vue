<script setup lang="ts">
import { computed } from 'vue'

import { CalendarCheck, Clock, EllipsisVertical, Pencil, Scale, Ticket, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import type { VoucherAccount, VoucherEntryRead, VoucherShift } from '@/client/types.gen'
import { parseServerDate } from '@/lib/server-time'
import {
  type VoucherHistoryItem,
  signedVoucherAmount,
  upcomingVoucherShifts,
  voucherHistory,
} from '@/lib/vouchers'

/**
 * Where someone's vouchers came from and went: every shift that earned some,
 * every redemption and every correction, newest first, each behind a tile
 * that says which of the three it is. Organisers get a menu on each
 * correction to change or delete it.
 *
 * `withUpcoming` (the volunteer's own page) puts the booked shifts whose
 * vouchers are still to come on top, under "Still to come", and the rest
 * under "So far". Without it (an organiser's dialog) the list is one, with
 * lines between the rows.
 */
const props = defineProps<{
  account: Pick<VoucherAccount, 'shifts' | 'entries'>
  canEdit?: boolean
  withUpcoming?: boolean
}>()

const emit = defineEmits<{
  edit: [entry: VoucherEntryRead]
  delete: [entry: VoucherEntryRead]
}>()

const { t, locale } = useI18n()
const { formatDateLabel, formatTimeRange, hour12 } = useFormatters()

const items = computed(() => voucherHistory(props.account))
const upcoming = computed(() => (props.withUpcoming ? upcomingVoucherShifts(props.account) : []))
const grouped = computed(() => upcoming.value.length > 0)

/** "Sat, 18 July · 17:00 – 20:00": a shift's day and times, as the rota reads them. */
function shiftWhen(shift: VoucherShift): string {
  const day = formatDateLabel(shift.date, { weekday: 'short', day: 'numeric', month: 'long' })
  const times = formatTimeRange(shift.start_time, shift.end_time)
  return times ? `${day} · ${times}` : day
}

/** Entries carry naive UTC; shown in the reader's own time: "Sat, 18 July, 15:03". */
function entryWhen(entry: VoucherEntryRead): string {
  const d = parseServerDate(entry.created_at)
  if (!d) return ''
  return d.toLocaleString(locale.value, {
    weekday: 'short',
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
    hour12: hour12.value,
  })
}

/** Who did it: "by Pia" took the vouchers at a stand, "by Anna" made the correction. */
function entrySub(entry: VoucherEntryRead): string {
  const when = entryWhen(entry)
  if (!entry.actor_name) return when
  const who =
    entry.kind === 'redemption'
      ? t('vouchers.history.redeemedBy', { name: entry.actor_name })
      : t('vouchers.history.by', { name: entry.actor_name })
  return when ? `${when} · ${who}` : who
}

const TONES = {
  shift: 'bg-primary/12 text-primary',
  redemption: 'bg-muted text-foreground/80',
  adjustment: 'bg-warning/12 text-warning',
}

function tone(item: VoucherHistoryItem): string {
  return item.kind === 'shift' ? TONES.shift : TONES[item.entry.kind]
}

function icon(item: VoucherHistoryItem) {
  if (item.kind === 'shift') return CalendarCheck
  return item.entry.kind === 'redemption' ? Ticket : Scale
}

function amount(item: VoucherHistoryItem): number {
  return item.kind === 'shift' ? item.shift.vouchers : item.entry.amount
}

const headingClass =
  'px-2 pt-2.5 pb-1 text-xs font-bold tracking-[0.05em] text-muted-foreground uppercase'
const tileClass = 'flex size-[38px] shrink-0 items-center justify-center rounded-xl sm:size-10'
</script>

<template>
  <div data-testid="voucher-history">
    <template v-if="grouped">
      <h3 :class="headingClass">{{ t('vouchers.history.upcoming') }}</h3>
      <ul>
        <li
          v-for="shift in upcoming"
          :key="`upcoming-${shift.booking_id}`"
          class="flex min-h-[52px] items-center gap-3 px-2 py-1.5 sm:min-h-14 sm:gap-3.5"
          data-testid="voucher-history-upcoming"
        >
          <span
            :class="tileClass"
            class="border-[1.5px] border-dashed border-muted-foreground/40 text-muted-foreground"
            aria-hidden="true"
          >
            <Clock class="size-[17px] sm:size-[18px]" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-[15px] font-semibold break-words">{{ shift.task_name }}</p>
            <p class="text-[13px] text-muted-foreground tabular-nums">{{ shiftWhen(shift) }}</p>
          </div>
          <span class="shrink-0 text-[15px] font-bold text-muted-foreground tabular-nums">
            {{ signedVoucherAmount(shift.vouchers) }}
          </span>
        </li>
      </ul>
      <h3 :class="headingClass" class="pt-3 sm:pt-3.5">{{ t('vouchers.history.past') }}</h3>
    </template>

    <p
      v-if="items.length === 0"
      class="text-sm text-muted-foreground"
      :class="grouped ? 'px-2 py-2' : 'py-4'"
    >
      {{ t('vouchers.history.empty') }}
    </p>
    <ul v-else>
      <li
        v-for="item in items"
        :key="item.key"
        class="flex gap-3"
        :class="
          withUpcoming
            ? 'min-h-[52px] items-start px-2 py-2 sm:min-h-14 sm:gap-3.5'
            : 'min-h-14 items-center border-b py-2 last:border-b-0'
        "
        :data-testid="item.kind === 'shift' ? 'voucher-history-shift' : 'voucher-history-entry'"
      >
        <span :class="[tileClass, tone(item)]" aria-hidden="true">
          <component :is="icon(item)" class="size-[17px] sm:size-[18px]" />
        </span>

        <div class="min-w-0 flex-1">
          <template v-if="item.kind === 'shift'">
            <p class="text-[15px] font-semibold break-words">
              {{ t('vouchers.history.shift', { task: item.shift.task_name }) }}
            </p>
            <p class="text-[13px] text-muted-foreground tabular-nums">
              {{ shiftWhen(item.shift) }}
            </p>
          </template>
          <template v-else>
            <p class="text-[15px] font-semibold break-words">
              {{
                item.entry.kind === 'redemption'
                  ? t('vouchers.history.redeemed', { place: item.entry.task_name ?? '?' })
                  : t('vouchers.history.adjustment')
              }}
            </p>
            <p
              v-if="item.entry.kind === 'adjustment' && item.entry.note"
              class="text-sm break-words text-foreground/85"
            >
              {{ item.entry.note }}
            </p>
            <p class="text-[13px] text-muted-foreground">{{ entrySub(item.entry) }}</p>
          </template>
        </div>

        <span
          class="shrink-0 text-[15px] font-bold tabular-nums"
          :class="[amount(item) > 0 ? 'text-primary' : '', withUpcoming ? 'pt-2' : '']"
        >
          {{ signedVoucherAmount(amount(item)) }}
        </span>

        <DropdownMenu v-if="canEdit && item.kind === 'entry' && item.entry.kind === 'adjustment'">
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="-mr-2 size-10 shrink-0 text-muted-foreground"
              :aria-label="t('vouchers.admin.correctionActions')"
              data-testid="btn-voucher-correction-actions"
            >
              <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem @select="emit('edit', item.entry)">
              <Pencil class="mr-2 size-4" />
              {{ t('vouchers.admin.editCorrection') }}
            </DropdownMenuItem>
            <DropdownMenuItem
              class="text-destructive focus:text-destructive"
              data-testid="btn-voucher-correction-delete"
              @select="emit('delete', item.entry)"
            >
              <Trash2 class="mr-2 size-4 text-destructive" />
              {{ t('vouchers.admin.deleteCorrection') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </li>
    </ul>
  </div>
</template>
