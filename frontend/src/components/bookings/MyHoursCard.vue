<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { ChevronRight, Clock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import HoursBreakdown from '@/components/events/HoursBreakdown.vue'

import type { VolunteerHoursDetail } from '@/client/types.gen'
import { formatHours } from '@/lib/format'

/**
 * The volunteer's hours in the selected event, on the bookings page beside
 * their vouchers.
 *
 * Like the vouchers card it reads the width of the page's `@container`:
 * narrow, a tile with "3 h", "worked, +6 planned" and a button to the
 * breakdown; from `@2xl` up the full card, with the hours large, what booked
 * shifts will still add, and where the hours came from. The breakdown (which
 * shifts, which hours added by hand) opens as a sheet on a phone and a dialog
 * on a desktop. Hidden while the hours cannot be read, e.g. once the
 * volunteer is no longer in the event.
 */
defineOptions({ inheritAttrs: false })

const { t } = useI18n()
const { get } = useAuthenticatedClient()
const authStore = useAuthStore()

const detail = ref<VolunteerHoursDetail | null>(null)
const breakdownOpen = ref(false)

const eventId = computed(() => authStore.selectedEventId)
const userId = computed(() => authStore.profile?.id ?? null)

const hoursLabel = (minutes: number) => t('duties.hours.unit', { value: formatHours(minutes) })

const summary = computed(() => detail.value?.summary ?? null)

const isEmpty = computed(
  () =>
    !!summary.value &&
    summary.value.total_minutes === 0 &&
    summary.value.upcoming_shift_count === 0,
)

/** "worked, +6 planned": the tile's one line. */
const workedShort = computed(() => {
  const s = summary.value
  if (!s) return ''
  const worked = t('duties.hours.my.workedShort')
  if (s.upcoming_shift_minutes <= 0) return worked
  return `${worked}, ${t('duties.hours.my.plannedShort', { value: formatHours(s.upcoming_shift_minutes) })}`
})

/** "6 h more to come from booked shifts", singular for exactly one hour. */
const upcomingLine = computed(() => {
  const minutes = summary.value?.upcoming_shift_minutes ?? 0
  return t('duties.hours.my.upcomingLine', { value: formatHours(minutes) }, minutes === 60 ? 1 : 2)
})

async function load() {
  detail.value = null
  if (!eventId.value || !userId.value) return
  try {
    const res = await get<{ data: VolunteerHoursDetail }>({
      url: `/events/${eventId.value}/hours/${userId.value}`,
    })
    detail.value = res.data
  } catch {
    // Not in the selected event (any more) — the card simply stays hidden.
  }
}

watch([eventId, userId], load)
onMounted(load)
</script>

<template>
  <section
    v-if="detail && summary"
    v-bind="$attrs"
    data-testid="my-hours-card"
    aria-labelledby="bookings-hours-title"
    class="flex min-w-0 flex-col rounded-2xl border bg-card p-4 text-card-foreground @2xl:rounded-[22px] @2xl:p-6"
  >
    <div class="flex items-center justify-between gap-1 @2xl:gap-2">
      <h2
        id="bookings-hours-title"
        class="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold text-muted-foreground @2xl:gap-2 @2xl:text-base @2xl:font-bold @2xl:text-card-foreground"
      >
        <Clock class="size-4 shrink-0 @2xl:size-[18px]" aria-hidden="true" />
        <span class="truncate @2xl:hidden">{{ t('duties.hours.my.titleShort') }}</span>
        <span class="hidden truncate @2xl:inline">{{ t('duties.hours.my.titleYour') }}</span>
      </h2>
      <template v-if="!isEmpty">
        <button
          type="button"
          :aria-label="t('duties.hours.my.breakdownLabel')"
          class="-my-3 -mr-3 flex size-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground outline-none hover:text-primary focus-visible:ring-[3px] focus-visible:ring-ring/50 @2xl:hidden"
          @click="breakdownOpen = true"
        >
          <ChevronRight class="size-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          class="-my-2 hidden min-h-8 items-center rounded-md px-1 text-sm font-semibold text-primary outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 @2xl:flex"
          data-testid="btn-toggle-hours-breakdown"
          @click="breakdownOpen = true"
        >
          {{ t('duties.hours.my.breakdown') }}
        </button>
      </template>
    </div>

    <!-- The tile: the hours and one line -->
    <div class="@2xl:hidden">
      <p class="mt-1.5 text-[2rem] leading-none font-bold tabular-nums">
        {{ hoursLabel(summary.total_minutes) }}
      </p>
      <p class="mt-1 text-[13px] text-muted-foreground" data-testid="my-hours-short">
        {{ workedShort }}
      </p>
    </div>

    <!-- The card: the hours large, what is still to come, where they came from -->
    <div class="hidden @2xl:block">
      <p class="mt-3.5 flex items-baseline gap-2">
        <span
          class="text-[3.25rem] leading-none font-bold tabular-nums"
          data-testid="my-hours-total"
        >
          {{ formatHours(summary.total_minutes) }}
        </span>
        <span class="text-[15px] text-muted-foreground">{{
          t('duties.hours.my.workedCaption')
        }}</span>
      </p>
      <p v-if="isEmpty" class="mt-1.5 text-sm text-foreground/80">
        {{ t('duties.hours.my.empty') }}
      </p>
      <template v-else>
        <p
          v-if="summary.upcoming_shift_minutes > 0"
          class="mt-1.5 text-sm text-foreground/80"
          data-testid="my-hours-upcoming"
        >
          {{ upcomingLine }}
        </p>
        <dl class="mt-3.5 grid grid-cols-2 gap-2">
          <div class="min-w-0 rounded-xl bg-muted/60 px-3 py-2.5">
            <dt class="truncate text-xs text-muted-foreground">
              {{ t('duties.hours.my.fromShifts') }}
            </dt>
            <dd class="mt-0.5 text-xl font-bold tabular-nums">
              {{ hoursLabel(summary.shift_minutes) }}
            </dd>
          </div>
          <div class="min-w-0 rounded-xl bg-muted/60 px-3 py-2.5">
            <dt class="truncate text-xs text-muted-foreground">
              {{ t('duties.hours.my.manual') }}
            </dt>
            <dd class="mt-0.5 text-xl font-bold tabular-nums">
              {{ hoursLabel(summary.manual_minutes) }}
            </dd>
          </div>
        </dl>
      </template>
    </div>

    <div v-if="!isEmpty" class="mt-auto pt-3 @2xl:hidden">
      <Button
        variant="outline"
        class="h-auto min-h-11 w-full rounded-[10px] bg-background px-3 py-2 text-sm leading-tight font-semibold whitespace-normal shadow-none"
        data-testid="btn-hours-breakdown-tile"
        @click="breakdownOpen = true"
      >
        {{ t('duties.hours.my.breakdown') }}
      </Button>
    </div>
  </section>

  <ResponsiveDialog v-model:open="breakdownOpen">
    <ResponsiveDialogContent dialog-class="sm:max-w-lg" data-testid="my-hours-breakdown">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>{{ t('duties.hours.my.title') }}</ResponsiveDialogTitle>
        <ResponsiveDialogDescription>{{
          t('duties.hours.my.subtitle')
        }}</ResponsiveDialogDescription>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody class="pb-6">
        <HoursBreakdown v-if="detail" :detail="detail" />
      </ResponsiveDialogBody>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
