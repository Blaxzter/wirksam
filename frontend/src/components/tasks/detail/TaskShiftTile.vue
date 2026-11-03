<script setup lang="ts">
import { computed } from 'vue'

import { CalendarX2, Check, Expand, Lock, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { ShiftRead } from '@/client/types.gen'
import { cn } from '@/lib/utils'

/**
 * One shift on the task page: its time, a bar of how full it is and a badge
 * saying so in words ("Full", "Nobody yet", "2 free").
 *
 * The whole tile is one button (`select`): the page decides what that does,
 * booking for a volunteer or opening the shift for whoever runs the task. A
 * delete button for those who may change the shifts, or a details button for
 * everyone else, sit on top of it rather than inside it, so no button is
 * nested in another.
 *
 * `compact` is the phone tile of the two-column grid: the badge moves under
 * the bar and carries the count ("2 of 3") itself.
 */
const props = defineProps<{
  shift: ShiftRead
  /** The viewer has booked it. */
  mine?: boolean
  /** A booking or cancellation for it is on the way. */
  busy?: boolean
  /** The viewer runs the task: the tile opens the shift instead of booking it. */
  manage?: boolean
  /** Why it can't be booked any more (over, or a voucher shift under way), or null. */
  note?: string | null
  /** Show the delete button: the viewer may change the task's shifts. */
  canDelete?: boolean
  /** Where or what, when the task's shifts differ in that ("Bar · Hall 2"). */
  meta?: string | null
  compact?: boolean
}>()

const emit = defineEmits<{
  select: []
  details: []
  delete: []
}>()

const { t } = useI18n()
const { formatTimeRange } = useFormatters()

const taken = computed(() => props.shift.current_bookings ?? 0)
const capacity = computed(() => props.shift.max_bookings ?? 1)
const full = computed(() => taken.value >= capacity.value)
const fill = computed(() =>
  capacity.value > 0 ? Math.min(100, Math.round((taken.value / capacity.value) * 100)) : 0,
)

const time = computed(
  () => formatTimeRange(props.shift.start_time, props.shift.end_time) || props.shift.title,
)

const countText = computed(() =>
  t('duties.tasks.detail.tileTaken', { taken: taken.value, max: capacity.value }),
)

const badge = computed(() => {
  if (full.value) {
    return { text: t('duties.tasks.detail.tileFull'), tone: 'bg-primary/12 text-primary' }
  }
  if (taken.value === 0) {
    // Amber asks for people; a shift that is over or under way can't take
    // any more, so it says so in grey like its other words.
    return {
      text: t('duties.tasks.detail.tileNobody'),
      tone: props.note ? 'bg-muted text-muted-foreground' : 'bg-warning/12 text-warning',
    }
  }
  return {
    // On a phone the badge is the only place the count is written.
    text: props.compact
      ? countText.value
      : t('duties.tasks.detail.tileFree', { n: capacity.value - taken.value }),
    tone: 'bg-muted text-muted-foreground',
  }
})

const locked = computed(() => !props.mine && !!props.shift.locked_by_team)
const clashes = computed(() => !props.mine && !!props.shift.collides_with_my_booking)

/** Why the tile looks greyed out, for the hint and the button's name. */
const hint = computed<string | null>(() => {
  if (props.mine) return null
  if (props.note) return props.note
  if (locked.value) return t('teamLocks.gate.lockedShift', { name: props.shift.team_name })
  if (clashes.value) return t('duties.shifts.detail.clashesWithMine')
  return null
})

const label = computed(() =>
  [time.value, countText.value, props.mine ? t('duties.tasks.detail.booked') : null, hint.value]
    .filter(Boolean)
    .join(', '),
)

/** A volunteer can do nothing with a full shift they are not on. */
const inert = computed(() => !props.manage && !props.mine && full.value)

const tileClass = computed(() =>
  cn(
    'group relative flex min-w-0 flex-col rounded-xl border bg-card text-card-foreground transition-colors select-none',
    props.compact ? 'gap-2 p-3' : 'gap-2.5 p-3.5',
    props.mine
      ? 'border-primary bg-primary/5 ring-1 ring-primary'
      : inert.value
        ? 'opacity-50'
        : props.note
          ? 'bg-muted/40 text-muted-foreground shadow-none'
          : locked.value
            ? 'border-dashed bg-muted/40 text-muted-foreground'
            : clashes.value
              ? 'border-dashed border-destructive/50'
              : 'hover:border-primary/50',
    props.busy && 'pointer-events-none opacity-60',
  ),
)
</script>

<template>
  <div :data-testid="`shift-card-${shift.id}`" :class="tileClass">
    <!-- The tile's own action, stretched over all of it -->
    <HintTooltip :label="hint">
      <button
        type="button"
        class="absolute inset-0 z-[1] rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        :class="inert ? 'cursor-not-allowed' : 'cursor-pointer'"
        :aria-label="label"
        :aria-disabled="inert || undefined"
        :disabled="busy"
        @click="emit('select')"
      />
    </HintTooltip>

    <div class="flex min-w-0 items-start justify-between gap-2">
      <!-- Wraps rather than cuts off: "10:00 AM – 11:30 AM" is long for a tile -->
      <span class="flex min-w-0 items-center gap-1.5">
        <span
          class="min-w-0 leading-snug font-bold break-words tabular-nums"
          :class="compact ? 'text-[15px]' : 'text-base'"
        >
          {{ time }}
        </span>
        <Check v-if="mine" class="size-4 shrink-0 text-primary" aria-hidden="true" />
        <CalendarX2
          v-else-if="clashes"
          class="size-4 shrink-0 text-destructive"
          aria-hidden="true"
          :data-testid="`shift-clash-${shift.id}`"
        />
        <Lock
          v-else-if="locked"
          class="size-3.5 shrink-0 text-muted-foreground"
          aria-hidden="true"
          :data-testid="`shift-team-locked-${shift.id}`"
        />
      </span>
      <span
        v-if="!compact"
        class="shrink-0 rounded-full px-2 py-0.5 text-xs font-bold"
        :class="badge.tone"
      >
        {{ badge.text }}
      </span>
      <template v-else>
        <HintTooltip v-if="canDelete" :label="t('duties.shifts.delete')">
          <button
            type="button"
            class="relative z-[2] -my-2.5 -mr-2.5 flex size-11 shrink-0 items-center justify-center rounded-lg text-destructive outline-none hover:bg-destructive/10 focus-visible:ring-[3px] focus-visible:ring-ring/50"
            :aria-label="t('duties.shifts.delete')"
            @click.stop="emit('delete')"
          >
            <Trash2 class="size-4" aria-hidden="true" />
          </button>
        </HintTooltip>
        <button
          v-else-if="!manage"
          type="button"
          class="relative z-[2] -my-2.5 -mr-2.5 flex size-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50"
          :aria-label="t('duties.shifts.detail.openDetails')"
          @click.stop="emit('details')"
        >
          <Expand class="size-4" aria-hidden="true" />
        </button>
      </template>
    </div>

    <p v-if="meta" class="-mt-1 truncate text-xs text-muted-foreground">{{ meta }}</p>

    <span
      aria-hidden="true"
      class="block overflow-hidden rounded-full bg-muted"
      :class="compact ? 'h-[5px]' : 'h-1.5'"
    >
      <span
        class="block h-full rounded-full"
        :class="full ? 'bg-primary' : 'bg-staff-partial'"
        :style="{ width: `${fill}%` }"
      />
    </span>

    <span
      v-if="compact"
      class="self-start rounded-full px-2 py-px text-xs font-bold"
      :class="badge.tone"
    >
      {{ badge.text }}
    </span>
    <div v-else class="flex min-h-6 items-center justify-between gap-2">
      <span class="truncate text-[13px] text-muted-foreground">{{ countText }}</span>
      <HintTooltip v-if="canDelete" :label="t('duties.shifts.delete')">
        <button
          type="button"
          class="relative z-[2] -my-1.5 -mr-1.5 flex size-8 shrink-0 items-center justify-center rounded-md text-destructive outline-none hover:bg-destructive/10 focus-visible:ring-[3px] focus-visible:ring-ring/50"
          :aria-label="t('duties.shifts.delete')"
          @click.stop="emit('delete')"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </button>
      </HintTooltip>
      <HintTooltip v-else-if="!manage" :label="t('duties.shifts.detail.openDetails')">
        <button
          type="button"
          class="relative z-[2] -my-1.5 -mr-1.5 flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 outline-none group-hover:opacity-100 hover:bg-muted focus-visible:opacity-100 focus-visible:ring-[3px] focus-visible:ring-ring/50"
          :aria-label="t('duties.shifts.detail.openDetails')"
          @click.stop="emit('details')"
        >
          <Expand class="size-4" aria-hidden="true" />
        </button>
      </HintTooltip>
    </div>
  </div>
</template>
