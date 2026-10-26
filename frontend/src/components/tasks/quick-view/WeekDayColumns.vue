<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { ChevronLeft, ChevronRight, Loader2, Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import Button from '@/components/ui/button/Button.vue'

import HintTooltip from '@/components/utils/HintTooltip.vue'

export interface DayShiftEntry {
  slotId: string
  startTime?: string | null
  endTime?: string | null
  currentBookings?: number
  maxBookings?: number
  isBookedByMe?: boolean
  /** Overlaps a shift the user already holds, so booking it would be refused. */
  collidesWithMyBooking?: boolean
  /** Reserved for a team the user is not in; the dialog offers to join. */
  lockedByTeam?: boolean
}

export interface DayColumn {
  date: Date
  dateStr: string
  shifts: DayShiftEntry[]
}

const props = defineProps<{
  days: DayColumn[]
  visibleDays?: number
  expanded?: boolean
  hideFullShifts?: boolean
  /** More days exist after the last one shown; swiping there asks for them. */
  hasMoreNext?: boolean
  /** Likewise before the first one. */
  hasMorePrevious?: boolean
  loadingNext?: boolean
  loadingPrevious?: boolean
  /** The team a locked chip is reserved for, named in its tooltip. */
  teamName?: string | null
}>()

const emit = defineEmits<{
  loadNext: []
  loadPrevious: []
  clickShift: [slotId: string]
  toggleExpand: []
}>()

const { t, locale } = useI18n()
const { formatTime } = useFormatters()

const COLLAPSED_LIMIT = 4

const cols = computed(() => props.visibleDays ?? 5)

const today = computed(() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

function filteredShifts(day: DayColumn): DayShiftEntry[] {
  if (!props.hideFullShifts) return day.shifts
  return day.shifts.filter((s) => slotHasCapacity(s))
}

const maxShiftCount = computed(() => {
  if (props.expanded) return Math.max(...props.days.map((d) => filteredShifts(d).length), 0)
  return Math.min(Math.max(...props.days.map((d) => filteredShifts(d).length), 0), COLLAPSED_LIMIT)
})

const totalHidden = computed(() => {
  if (props.expanded) return 0
  return props.days.reduce(
    (sum, d) => sum + Math.max(0, filteredShifts(d).length - COLLAPSED_LIMIT),
    0,
  )
})

function columnHidden(day: DayColumn): number {
  if (props.expanded) return 0
  return Math.max(0, filteredShifts(day).length - COLLAPSED_LIMIT)
}

function visibleShifts(day: DayColumn) {
  const shifts = filteredShifts(day)
  if (props.expanded) return shifts
  return shifts.slice(0, COLLAPSED_LIMIT)
}

function formatDayLabel(date: Date): string {
  return date.toLocaleDateString(locale.value, { weekday: 'short' })
}

function formatDayDate(date: Date): string {
  return date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

function slotHasCapacity(shift: DayShiftEntry): boolean {
  if (!shift.maxBookings) return true
  return (shift.currentBookings ?? 0) < shift.maxBookings
}

function slotClasses(shift: DayShiftEntry): string {
  if (shift.isBookedByMe) {
    return 'border-green-500/40 bg-green-500/15 text-green-700 dark:text-green-400 font-semibold hover:bg-green-500/25'
  }
  if (shift.lockedByTeam) {
    return 'border-dashed border-muted-foreground/40 text-muted-foreground hover:bg-muted/50'
  }
  if (shift.collidesWithMyBooking) {
    return 'border-dashed border-destructive/50 text-destructive opacity-70 hover:opacity-90 hover:bg-destructive/10'
  }
  if (slotHasCapacity(shift)) {
    return 'border-primary/30 text-primary hover:bg-primary/10'
  }
  return 'border-muted text-muted-foreground opacity-60 hover:opacity-80 hover:bg-muted/50'
}

/**
 * Whether the guided tour may open this chip.
 *
 * Three ways a chip is a dead end for the tour: it is full, the visitor is
 * already on it, or it is behind them. The seeder used to hand the tour the
 * first chip on the board, which is exactly the one it had booked the guest
 * into — so the "Book shift" button the step highlights did not render at all.
 *
 * A string rather than a boolean binding because Vue drops a `false` attribute
 * entirely, and `[data-tour-bookable="false"]` is worth being able to select.
 */
function tourBookable(day: DayColumn, shift: DayShiftEntry): 'true' | 'false' {
  if (shift.isBookedByMe) return 'false'
  if (shift.lockedByTeam) return 'false'
  if (!slotHasCapacity(shift)) return 'false'
  return day.dateStr >= today.value ? 'true' : 'false' // ISO dates compare lexicographically
}

/** Why a chip cannot be booked, for its tooltip and accessible name. */
function chipTitle(shift: DayShiftEntry): string | undefined {
  if (shift.isBookedByMe) return undefined
  if (shift.lockedByTeam) return t('teamLocks.badge.locked', { name: props.teamName ?? '' })
  if (shift.collidesWithMyBooking) return t('duties.shifts.detail.clashesWithMine')
  return undefined
}

function slotCountClasses(shift: DayShiftEntry): string {
  if (shift.isBookedByMe) return 'text-green-600/70 dark:text-green-400/70'
  if (shift.lockedByTeam) return 'text-muted-foreground'
  if (shift.collidesWithMyBooking) return 'text-destructive/80'
  if (slotHasCapacity(shift)) return 'text-primary'
  return 'text-muted-foreground'
}

/*
 * One horizontal scroller, a column per day, `visibleDays` of them filling its
 * width. Later days load as a sentinel after the last column nears view; it is
 * in reach from the start, so the next days arrive at once and the strip can
 * be swiped at all. Earlier days cannot work that way — the strip opens at its
 * start, with nothing to its left to scroll into — so they load on the first
 * touch of the strip and whenever a scroll comes near the start; the columns
 * added in front are then kept out of sight until swiped to.
 */
const scroller = ref<HTMLElement | null>(null)
const tailSentinel = ref<HTMLElement | null>(null)
const NEAR_EDGE_PX = 120
let observer: IntersectionObserver | null = null
let pageBackPending = false

const atStart = ref(true)
const atEnd = ref(false)

function updateEdges() {
  const el = scroller.value
  if (!el) return
  atStart.value = el.scrollLeft <= 1
  atEnd.value = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1
}

function requestPrevious() {
  if (props.hasMorePrevious && !props.loadingPrevious) emit('loadPrevious')
}

function onScroll() {
  updateEdges()
  if ((scroller.value?.scrollLeft ?? Infinity) < NEAR_EDGE_PX) requestPrevious()
}

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting) && props.hasMoreNext) emit('loadNext')
    },
    { root: scroller.value, rootMargin: `0px ${NEAR_EDGE_PX}px` },
  )
  if (tailSentinel.value) observer.observe(tailSentinel.value)
  updateEdges()
})

onBeforeUnmount(() => observer?.disconnect())

// Days added in front would push the visible ones right; keep them in place.
watch(
  () => props.days[0]?.dateStr,
  async (first, before) => {
    const el = scroller.value
    if (!el || !first || !before || first >= before) return
    const widthBefore = el.scrollWidth
    const leftBefore = el.scrollLeft
    await nextTick()
    el.scrollLeft = leftBefore + (el.scrollWidth - widthBefore)
    updateEdges()
    // The ‹ arrow asked for these days: now go back to them.
    if (pageBackPending) {
      pageBackPending = false
      el.scrollBy({ left: -el.clientWidth, behavior: 'smooth' })
    }
  },
  { flush: 'pre' },
)

watch(
  () => props.days.length,
  () => nextTick(updateEdges),
)

/** Arrow buttons (wider screens): a screenful of days at a time. */
function page(direction: 1 | -1) {
  const el = scroller.value
  if (!el) return
  if (direction === -1 && atStart.value && props.hasMorePrevious) {
    pageBackPending = true
    emit('loadPrevious')
    return
  }
  if (direction === 1 && atEnd.value && props.hasMoreNext) emit('loadNext')
  el.scrollBy({ left: direction * el.clientWidth, behavior: 'smooth' })
}

const canGoPrevious = computed(() => !atStart.value || !!props.hasMorePrevious)
const canGoNext = computed(() => !atEnd.value || !!props.hasMoreNext)

defineExpose({ totalHidden, maxShiftCount })
</script>

<template>
  <div class="flex h-full items-stretch">
    <HintTooltip :label="t('duties.tasks.quickView.previousDays')">
      <button
        class="hidden w-6 shrink-0 items-start justify-center pt-3 text-muted-foreground hover:text-foreground disabled:opacity-30 md:flex"
        :aria-label="t('duties.tasks.quickView.previousDays')"
        :disabled="!canGoPrevious"
        @click="page(-1)"
      >
        <ChevronLeft class="h-4 w-4" />
      </button>
    </HintTooltip>

    <div
      ref="scroller"
      data-testid="day-strip"
      class="flex min-w-0 flex-1 snap-x snap-mandatory overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      @scroll.passive="onScroll"
      @pointerdown.once="requestPrevious"
    >
      <!-- Swiped to the start: earlier days load here. -->
      <div
        class="flex shrink-0 items-center justify-center"
        :class="loadingPrevious ? 'w-8' : 'w-px'"
        aria-hidden="true"
      >
        <Loader2 v-if="loadingPrevious" class="size-4 animate-spin text-muted-foreground" />
      </div>

      <!-- Phones see a sliver of the next day at the edge: the strip swipes. -->
      <div
        v-for="day in days"
        :key="day.dateStr"
        :data-testid="`day-column-${day.dateStr}`"
        class="flex w-[calc(100%/var(--cols))] shrink-0 snap-start flex-col rounded-md max-md:w-[calc(100%/(var(--cols)+0.4))]"
        :class="day.dateStr === today ? 'bg-primary/5' : ''"
        :style="{ '--cols': cols }"
      >
        <div class="px-1 py-1.5 text-center">
          <div
            class="text-xs font-medium"
            :class="day.dateStr === today ? 'text-primary' : 'text-muted-foreground'"
          >
            {{ formatDayLabel(day.date) }}
          </div>
          <div
            class="text-xs"
            :class="day.dateStr === today ? 'text-primary font-semibold' : 'text-muted-foreground'"
          >
            {{ formatDayDate(day.date) }}
          </div>
        </div>

        <div class="flex flex-1 flex-col gap-1 px-1 py-1">
          <template v-if="filteredShifts(day).length > 0">
            <Button
              v-for="shift in visibleShifts(day)"
              :key="shift.slotId"
              :data-testid="'shift-chip-' + shift.slotId"
              :data-tour-bookable="tourBookable(day, shift)"
              :data-tour-booked-by-me="shift.isBookedByMe ? 'true' : 'false'"
              :data-tour-full="slotHasCapacity(shift) ? 'false' : 'true'"
              variant="outline"
              size="sm"
              class="h-auto w-full px-1.5 py-1 text-xs"
              :class="slotClasses(shift)"
              :title="chipTitle(shift)"
              :aria-label="
                chipTitle(shift)
                  ? `${formatTime(shift.startTime) || '—'}, ${chipTitle(shift)}`
                  : undefined
              "
              :data-team-locked="shift.lockedByTeam && !shift.isBookedByMe ? 'true' : undefined"
              @click="emit('clickShift', shift.slotId)"
            >
              <div class="flex w-full flex-col items-center gap-0.5">
                <span class="inline-flex items-center gap-1">
                  {{ formatTime(shift.startTime) || '—' }}
                  <Lock
                    v-if="shift.lockedByTeam && !shift.isBookedByMe"
                    class="size-2.5"
                    aria-hidden="true"
                  />
                </span>
                <span class="text-[10px] leading-none" :class="slotCountClasses(shift)">
                  {{ shift.currentBookings ?? 0 }}/{{ shift.maxBookings ?? '—' }}
                </span>
              </div>
            </Button>
            <!-- Per-column show more -->
            <button
              v-if="columnHidden(day) > 0"
              class="mt-0.5 rounded px-1 py-1 text-center text-[10px] font-medium text-primary hover:bg-primary/10"
              @click="emit('toggleExpand')"
            >
              {{ t('duties.tasks.quickView.showMore', { count: columnHidden(day) }) }}
            </button>
          </template>
          <!-- Per-column show less -->
          <button
            v-if="expanded && filteredShifts(day).length > COLLAPSED_LIMIT"
            class="mt-0.5 rounded px-1 py-1 text-center text-[10px] font-medium text-muted-foreground hover:bg-muted/50"
            @click="emit('toggleExpand')"
          >
            {{ t('duties.tasks.quickView.showLess') }}
          </button>
          <!-- Empty day: show dash, flex-grow to fill height -->
          <div
            v-if="filteredShifts(day).length === 0"
            class="flex flex-1 items-center justify-center text-xs text-muted-foreground"
          >
            —
          </div>
        </div>
      </div>

      <!-- Swiped to the end: later days load here. -->
      <div
        ref="tailSentinel"
        class="flex shrink-0 items-center justify-center"
        :class="loadingNext ? 'w-8' : 'w-px'"
        aria-hidden="true"
      >
        <Loader2 v-if="loadingNext" class="size-4 animate-spin text-muted-foreground" />
      </div>
    </div>

    <HintTooltip :label="t('duties.tasks.quickView.nextDays')">
      <button
        class="hidden w-6 shrink-0 items-start justify-center pt-3 text-muted-foreground hover:text-foreground disabled:opacity-30 md:flex"
        :aria-label="t('duties.tasks.quickView.nextDays')"
        :disabled="!canGoNext"
        @click="page(1)"
      >
        <ChevronRight class="h-4 w-4" />
      </button>
    </HintTooltip>
  </div>
</template>
