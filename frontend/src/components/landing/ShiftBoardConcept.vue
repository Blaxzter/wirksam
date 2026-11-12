<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'

import { CheckIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

/**
 * The hero illustration: a roster board, drawn rather than photographed.
 *
 * The hero used to lead with a dashboard screenshot, which showed a lot of
 * chrome and very little of the idea. This is the idea — days across, shifts
 * down, and how full each one is — so a visitor understands the product before
 * reading a word. Being drawn from theme tokens, it also can't go stale when
 * the app is redesigned, and needs no light/dark capture.
 *
 * It plays the story once as it scrolls into view: the shifts arrive empty and
 * fill up, place by place, the way a roster actually does. Places are taken in
 * round-robin passes rather than one shift at a time, so it reads as a team
 * signing up rather than a progress bar.
 */
const { t } = useI18n()

type Fill = 'full' | 'partial' | 'open'

interface SlotDef {
  id: string
  time: string
  /** Places on the shift. */
  of: number
  /** Places taken once the sequence has finished. */
  target: number
  /** The one slot presented as the visitor's own booking. */
  mine?: boolean
}

const DAYS: { key: string; slots: Omit<SlotDef, 'id'>[] }[] = [
  {
    key: '0',
    slots: [
      { time: '09:00', of: 2, target: 2 },
      { time: '10:30', of: 2, target: 2 },
      { time: '12:00', of: 2, target: 1 },
      { time: '13:30', of: 2, target: 2 },
    ],
  },
  {
    key: '1',
    slots: [
      { time: '09:00', of: 2, target: 2 },
      { time: '10:30', of: 2, target: 2, mine: true },
      { time: '12:00', of: 2, target: 2 },
      { time: '13:30', of: 2, target: 0 },
    ],
  },
  {
    key: '2',
    slots: [
      { time: '09:00', of: 2, target: 1 },
      { time: '10:30', of: 2, target: 2 },
      { time: '12:00', of: 2, target: 0 },
      { time: '13:30', of: 2, target: 1 },
    ],
  },
]

const days = DAYS.map((day) => ({
  key: day.key,
  slots: day.slots.map((slot, index): SlotDef => ({ ...slot, id: day.key + '-' + index })),
}))

const allSlots = days.flatMap((day) => day.slots)

const taken = ref<Record<string, number>>(Object.fromEntries(allSlots.map((s) => [s.id, 0])))
const revealed = ref(false)
const youVisible = ref(false)

function fillOf(slot: SlotDef): Fill {
  const count = taken.value[slot.id] ?? 0
  if (count === 0) return 'open'
  return count >= slot.of ? 'full' : 'partial'
}

/** Derived, so the badge can never contradict the grid under it. */
const openPlaces = computed(() =>
  allSlots.reduce((total, slot) => total + (slot.of - (taken.value[slot.id] ?? 0)), 0),
)

const legend: Fill[] = ['full', 'partial', 'open']

// `partial` mirrors `full`'s shape against `--warning` rather than `--primary`,
// so the two states differ by hue alone and stay apart in both themes. It used
// to borrow `--accent`, which is the hover surface — see the note in index.css.
const chipClass: Record<Fill, string> = {
  full: 'border-primary/35 bg-primary/12 text-foreground',
  partial: 'border-warning/55 bg-warning/8 text-foreground',
  open: 'border-dashed border-border bg-transparent text-muted-foreground',
}

const dotClass: Record<Fill, string> = {
  full: 'bg-primary',
  partial: 'bg-warning',
  open: 'border border-dashed border-muted-foreground/60',
}

// ── The sequence ────────────────────────────────────────────────────────────

/** Delay before the first booking lands, covering the chips' own fade-in. */
const SETTLE_MS = 700
/** Gap between one place being taken and the next. */
const STEP_MS = 130

const timers: ReturnType<typeof setTimeout>[] = []
const board = useTemplateRef<HTMLElement>('board')
let observer: IntersectionObserver | undefined

function finish() {
  for (const slot of allSlots) taken.value[slot.id] = slot.target
  revealed.value = true
  youVisible.value = true
}

function play() {
  revealed.value = true

  // One place per shift per pass, so the board fills evenly instead of
  // completing each shift before moving on to the next.
  const bookings: string[] = []
  const deepest = Math.max(...allSlots.map((slot) => slot.target))
  for (let pass = 0; pass < deepest; pass += 1) {
    for (const slot of allSlots) {
      if (slot.target > pass) bookings.push(slot.id)
    }
  }

  bookings.forEach((id, index) => {
    timers.push(
      setTimeout(
        () => {
          taken.value[id] = (taken.value[id] ?? 0) + 1
        },
        SETTLE_MS + index * STEP_MS,
      ),
    )
  })

  timers.push(
    setTimeout(
      () => {
        youVisible.value = true
      },
      SETTLE_MS + bookings.length * STEP_MS + 250,
    ),
  )
}

onMounted(() => {
  // Motion is decorative here and the finished board is the informative state,
  // so anyone who asked for less of it simply gets that.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    finish()
    return
  }

  if (!board.value) {
    play()
    return
  }

  // Only worth playing while it is watched: someone who lands further down the
  // page should not come back to a board frozen mid-fill.
  observer = new IntersectionObserver(
    ([entry]) => {
      if (!entry.isIntersecting) return
      observer?.disconnect()
      play()
    },
    { threshold: 0.35 },
  )
  observer.observe(board.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  for (const timer of timers) clearTimeout(timer)
})
</script>

<template>
  <!-- One description for assistive tech, phrased as the finished board; the
       grid and its animation are decorative detail. -->
  <div
    ref="board"
    role="img"
    :aria-label="t('preauth.landing.hero.board.summary')"
    class="rounded-2xl border bg-card/80 p-4 shadow-xl ring-1 ring-black/5 backdrop-blur sm:p-6"
  >
    <div aria-hidden="true">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-sm font-semibold">{{ t('preauth.landing.hero.board.taskName') }}</p>
        <span class="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
          {{ t('preauth.landing.hero.board.openCount', { count: openPlaces }, openPlaces) }}
        </span>
      </div>

      <div class="mt-4 grid grid-cols-3 gap-2 sm:gap-3">
        <div v-for="(day, dayIndex) in days" :key="day.key">
          <p
            class="pb-2 text-center text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
          >
            {{ t('preauth.landing.hero.board.days.' + day.key) }}
          </p>
          <ul class="space-y-2">
            <li
              v-for="(slot, slotIndex) in day.slots"
              :key="slot.id"
              class="relative rounded-lg border px-2 py-2 text-center transition-[color,background-color,border-color,opacity,transform] duration-500 sm:px-3"
              :class="[
                chipClass[fillOf(slot)],
                revealed ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0',
                slot.mine && youVisible ? 'ring-2 ring-primary ring-offset-2 ring-offset-card' : '',
              ]"
              :style="{
                transitionDelay: revealed ? (dayIndex * 4 + slotIndex) * 45 + 'ms' : '0ms',
              }"
            >
              <span class="block text-xs font-medium tabular-nums sm:text-sm">{{ slot.time }}</span>

              <!-- Keyed on the count so each new booking re-mounts and pops. -->
              <span
                :key="taken[slot.id]"
                class="mt-0.5 flex animate-in items-center justify-center gap-1 text-[11px] tabular-nums duration-300 zoom-in-75"
              >
                <CheckIcon v-if="fillOf(slot) === 'full'" class="size-3 text-primary" />
                {{ taken[slot.id] }}/{{ slot.of }}
              </span>

              <Transition
                enter-active-class="transition duration-300 ease-out"
                enter-from-class="scale-50 opacity-0"
                enter-to-class="scale-100 opacity-100"
              >
                <!-- The last thing to appear, which is how a test knows the board has
                     stopped moving. -->
                <span
                  v-if="slot.mine && youVisible"
                  data-testid="board-you"
                  class="absolute -right-1 -top-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground shadow-sm"
                >
                  {{ t('preauth.landing.hero.board.you') }}
                </span>
              </Transition>
            </li>
          </ul>
        </div>
      </div>

      <ul class="mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 border-t pt-3">
        <li
          v-for="state in legend"
          :key="state"
          class="flex items-center gap-1.5 text-[11px] text-muted-foreground"
        >
          <span class="size-2 rounded-full" :class="dotClass[state]" />
          {{ t('preauth.landing.hero.board.legend.' + state) }}
        </li>
      </ul>
    </div>
  </div>
</template>
