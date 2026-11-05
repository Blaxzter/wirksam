<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ScanLine, SlidersHorizontal, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import type { RouteLocationRaw } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'

import type { PointRedemptionList, TaskRead } from '@/client/types.gen'

/**
 * "Vouchers" on the task page: how many a shift here earns, whether this is a
 * place that takes them, and the way to the redeem page for whoever may take
 * them here right now.
 *
 * At a place that takes vouchers, the organisers and the people in charge
 * also see how many were redeemed here so far, over every day, from the same
 * read the redeem page lists its entries with (which shows today's figure).
 */
const props = defineProps<{
  task: TaskRead
  /** The viewer is an organiser: offer the voucher settings. */
  canAdmin?: boolean
  /** The viewer runs the task (organiser or in charge): show the count. */
  canManage?: boolean
  /** The viewer may redeem here right now. */
  canRedeem?: boolean
  /** Where "Redeem vouchers" goes. */
  redeemTo: RouteLocationRaw
  /** Phone layout. */
  compact?: boolean
}>()

const emit = defineEmits<{ settings: [] }>()

const { t } = useI18n()
const { get } = useAuthenticatedClient()

const perShift = computed(() => props.task.vouchers_per_shift ?? 0)
const isPoint = computed(() => !!props.task.is_voucher_point)
/** A place that took vouchers, until it was archived: the server now refuses them. */
const isArchivedPoint = computed(() => isPoint.value && props.task.status === 'archived')

/** Vouchers redeemed here on every day so far, or null when not shown. */
const redeemedHere = ref<number | null>(null)

async function loadRedeemed() {
  const tk = props.task
  if (!tk.event_id || !isPoint.value || !props.canRedeem || !props.canManage) {
    redeemedHere.value = null
    return
  }
  try {
    const res = await get<{ data: PointRedemptionList }>({
      url: `/events/${tk.event_id}/vouchers/points/${tk.id}/entries`,
      query: { limit: 1 },
    })
    if (props.task.id === tk.id) redeemedHere.value = res.data.total_amount
  } catch {
    // Only a number on a card; the tile falls back to "Takes vouchers".
    redeemedHere.value = null
  }
}

watch(() => [props.task.id, isPoint.value, props.canRedeem, props.canManage], loadRedeemed, {
  immediate: true,
})

const tileClass = computed(() =>
  props.compact ? 'rounded-xl px-3 py-2.5' : 'rounded-[14px] px-3.5 py-3',
)
/** The caption is the paragraph; the number leads it on a line of its own. */
const captionClass = computed(() =>
  props.compact ? 'text-xs text-muted-foreground' : 'text-[13px] text-muted-foreground',
)
const numberClass = computed(() =>
  props.compact
    ? 'mb-0.5 block text-2xl leading-tight font-bold text-foreground tabular-nums'
    : 'mb-0.5 block text-[28px] leading-tight font-bold text-foreground tabular-nums',
)
const emptyTileClass = computed(() => [
  tileClass.value,
  'flex items-center border border-dashed text-muted-foreground',
  props.compact ? 'text-xs' : 'text-[13px]',
])
</script>

<template>
  <section
    aria-labelledby="task-vouchers-title"
    data-testid="task-vouchers-card"
    class="flex min-w-0 flex-col border bg-card text-card-foreground"
    :class="compact ? 'gap-3 rounded-[18px] p-4' : 'gap-3.5 rounded-[20px] px-[22px] py-5'"
  >
    <div class="flex min-h-10 items-center justify-between gap-3">
      <h2 id="task-vouchers-title" class="flex items-center gap-2 text-base font-bold">
        <Ticket class="size-[18px] shrink-0 text-primary" aria-hidden="true" />
        {{ t('vouchers.title') }}
      </h2>
      <template v-if="canAdmin">
        <button
          v-if="compact"
          type="button"
          data-testid="btn-task-vouchers-card"
          class="-my-2 -mr-2 flex size-11 items-center justify-center rounded-lg text-muted-foreground outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50"
          :aria-label="t('vouchers.settings.open')"
          @click="emit('settings')"
        >
          <SlidersHorizontal class="size-[18px]" aria-hidden="true" />
        </button>
        <Button
          v-else
          variant="outline"
          data-testid="btn-task-vouchers-card"
          class="h-10 rounded-[10px] bg-background px-3.5 font-semibold shadow-none"
          @click="emit('settings')"
        >
          <SlidersHorizontal aria-hidden="true" />
          {{ t('vouchers.task.setUp') }}
        </Button>
      </template>
    </div>

    <div class="grid grid-cols-2" :class="compact ? 'gap-2' : 'gap-2.5'">
      <div
        v-if="perShift > 0"
        :class="[tileClass, 'bg-muted/70']"
        data-testid="task-vouchers-per-shift"
      >
        <!-- One sentence for a screen reader and for copying: "2 per shift, …" -->
        <p :class="captionClass">
          <span :class="numberClass">{{ perShift }}</span>
          {{ compact ? t('vouchers.task.perShiftShort') : t('vouchers.task.perShiftCaption') }}
        </p>
      </div>
      <div v-else :class="emptyTileClass">{{ t('vouchers.task.noneEarned') }}</div>

      <div
        v-if="isArchivedPoint"
        :class="emptyTileClass"
        data-testid="task-voucher-point-archived"
      >
        {{ t('vouchers.task.pointArchived') }}
      </div>
      <template v-else-if="isPoint">
        <div
          v-if="redeemedHere !== null"
          :class="[tileClass, 'bg-muted/70']"
          data-testid="task-voucher-point"
        >
          <p :class="captionClass">
            <span :class="numberClass" data-testid="task-vouchers-redeemed-here">
              {{ redeemedHere }}
            </span>
            {{ compact ? t('vouchers.task.redeemedHereShort') : t('vouchers.task.redeemedHere') }}
          </p>
        </div>
        <div
          v-else
          :class="[tileClass, 'flex items-center gap-2 bg-muted/70 font-semibold']"
          data-testid="task-voucher-point"
        >
          <ScanLine class="size-4 shrink-0 text-primary" aria-hidden="true" />
          <span :class="compact ? 'text-xs' : 'text-[13px]'">{{ t('vouchers.task.point') }}</span>
        </div>
      </template>
      <div v-else :class="emptyTileClass">
        {{ compact ? t('vouchers.task.notPointShort') : t('vouchers.task.notPoint') }}
      </div>
    </div>

    <Button
      v-if="canRedeem && isPoint"
      as-child
      class="mt-auto w-full rounded-xl font-bold"
      :class="compact ? 'h-[50px] text-base' : 'h-[46px] text-[15px]'"
    >
      <RouterLink :to="redeemTo" data-testid="btn-redeem-vouchers">
        <ScanLine class="size-[18px]" aria-hidden="true" />
        {{ t('vouchers.redeem.open') }}
      </RouterLink>
    </Button>

    <p v-if="compact && perShift > 0" class="text-[13px] text-muted-foreground">
      {{ t('vouchers.task.earnHint') }}
    </p>
  </section>
</template>
