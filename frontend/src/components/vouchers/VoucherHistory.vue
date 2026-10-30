<script setup lang="ts">
import { computed } from 'vue'

import { CalendarCheck, EllipsisVertical, Pencil, Scale, Ticket, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import type { VoucherAccount, VoucherEntryRead } from '@/client/types.gen'
import { parseServerDate } from '@/lib/server-time'
import { voucherHistory } from '@/lib/vouchers'

/**
 * Where someone's vouchers came from and went: every shift that earned some,
 * every redemption and every correction, newest first. Organisers get a menu
 * on each correction to change or delete it.
 */
const props = defineProps<{
  account: Pick<VoucherAccount, 'shifts' | 'entries'>
  canEdit?: boolean
}>()

const emit = defineEmits<{
  edit: [entry: VoucherEntryRead]
  delete: [entry: VoucherEntryRead]
}>()

const { t, locale } = useI18n()
const { formatDateLabel } = useFormatters()

const items = computed(() => voucherHistory(props.account))

/** Entries carry naive UTC; shown in the reader's own time. */
function when(iso: string): string {
  const d = parseServerDate(iso)
  if (!d) return ''
  return d.toLocaleString(locale.value, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "+2" and "−1", with a real minus sign. */
function signed(amount: number): string {
  if (amount > 0) return `+${amount}`
  return `−${Math.abs(amount)}`
}
</script>

<template>
  <div data-testid="voucher-history">
    <p v-if="items.length === 0" class="py-4 text-sm text-muted-foreground">
      {{ t('vouchers.history.empty') }}
    </p>
    <ul v-else class="divide-y">
      <li
        v-for="item in items"
        :key="item.key"
        class="flex items-start gap-3 py-2.5"
        :data-testid="item.kind === 'shift' ? 'voucher-history-shift' : 'voucher-history-entry'"
      >
        <template v-if="item.kind === 'shift'">
          <CalendarCheck class="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm">
              {{
                t('vouchers.history.shift', {
                  task: item.shift.task_name,
                  date: formatDateLabel(item.shift.date),
                })
              }}
            </p>
          </div>
          <span class="shrink-0 font-semibold tabular-nums text-green-700 dark:text-green-400">
            {{ signed(item.shift.vouchers) }}
          </span>
        </template>

        <template v-else>
          <component
            :is="item.entry.kind === 'redemption' ? Ticket : Scale"
            class="mt-0.5 size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <div class="min-w-0 flex-1 space-y-0.5">
            <p class="truncate text-sm">
              {{
                item.entry.kind === 'redemption'
                  ? t('vouchers.history.redeemed', { place: item.entry.task_name ?? '?' })
                  : t('vouchers.history.adjustment')
              }}
            </p>
            <p
              v-if="item.entry.kind === 'adjustment' && item.entry.note"
              class="text-sm break-words text-muted-foreground"
            >
              {{ item.entry.note }}
            </p>
            <p class="text-xs text-muted-foreground">
              {{ when(item.entry.created_at) }}
              <template v-if="item.entry.actor_name">
                · {{ t('vouchers.history.by', { name: item.entry.actor_name }) }}
              </template>
            </p>
          </div>
          <span
            class="shrink-0 font-semibold tabular-nums"
            :class="item.entry.amount > 0 ? 'text-green-700 dark:text-green-400' : ''"
          >
            {{ signed(item.entry.amount) }}
          </span>
          <DropdownMenu v-if="canEdit && item.entry.kind === 'adjustment'">
            <DropdownMenuTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="-my-1 size-8 shrink-0"
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
        </template>
      </li>
    </ul>
  </div>
</template>
