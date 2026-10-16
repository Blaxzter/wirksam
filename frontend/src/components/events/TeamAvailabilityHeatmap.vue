<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { UserAvailabilityWithUser } from '@/client/types.gen'

type AvailabilityType = 'fully_available' | 'specific_dates' | 'time_range'

const props = defineProps<{
  days: Date[]
  hours: number[]
  members: UserAvailabilityWithUser[]
  currentUserId?: string | null
  selfMode?: AvailabilityType | null
  selfPaint?: Set<string> | null
  selfDailyFrom?: number | null
  selfDailyTo?: number | null
  selfDailyExcluded?: Set<number> | null
}>()

const { t, locale } = useI18n()
const { formatDateLabel } = useFormatters()

function dateKey(d: Date) {
  return d.toISOString().slice(0, 10)
}

function heatFromHours(onCount: number): number {
  if (onCount === 0) return 0
  if (onCount < 4) return 1
  if (onCount < 9) return 2
  return 3
}

// Returns a 0..3 heat level for member×day.
function heatFor(m: UserAvailabilityWithUser, di: number): number {
  // Current user: reflect live (unsaved) edit state
  if (m.user_id === props.currentUserId && props.selfMode) {
    if (props.selfMode === 'fully_available') return 3
    if (props.selfMode === 'time_range') {
      if (props.selfDailyExcluded?.has(di)) return 0
      const start = props.selfDailyFrom ?? 9
      const end = props.selfDailyTo ?? 17
      return heatFromHours(Math.max(0, end - start))
    }
    if (props.selfPaint) {
      const onCount = props.hours.filter((h) => props.selfPaint!.has(`${di}-${h}`)).length
      return heatFromHours(onCount)
    }
  }

  if (m.availability_type === 'fully_available') return 3
  if (m.availability_type === 'time_range') {
    const start = m.default_start_time
    const end = m.default_end_time
    if (!start || !end) return 2
    const hrs = parseInt(end.slice(0, 2), 10) - parseInt(start.slice(0, 2), 10)
    return heatFromHours(hrs)
  }
  // specific_dates
  const k = dateKey(props.days[di])
  const hits = (m.available_dates ?? []).filter((d) => d.slot_date === k)
  if (hits.length === 0) return 0
  let onCount = 0
  for (const e of hits) {
    if (!e.start_time && !e.end_time) return 3
    const start = e.start_time ? parseInt(e.start_time.slice(0, 2), 10) : props.hours[0]
    const end = e.end_time
      ? parseInt(e.end_time.slice(0, 2), 10)
      : props.hours[props.hours.length - 1] + 1
    onCount += Math.max(0, end - start)
  }
  return heatFromHours(onCount)
}

const heatStyles = ['bg-muted', 'bg-primary/15', 'bg-primary/45', 'bg-primary/80']

const sortedMembers = computed(() => {
  const me = props.members.find((m) => m.user_id === props.currentUserId)
  const others = props.members.filter((m) => m.user_id !== props.currentUserId)
  return me ? [me, ...others] : others
})

function memberInitials(m: UserAvailabilityWithUser): string {
  const name = m.user_full_name ?? m.user_email ?? '?'
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function memberDisplayShort(m: UserAvailabilityWithUser): string {
  const name = m.user_full_name ?? m.user_email ?? '?'
  const parts = name.split(/\s+/)
  if (parts.length === 1) return parts[0]
  return `${parts[0]} ${parts[1][0]}.`
}
</script>

<template>
  <div class="space-y-3">
    <!-- Day header row -->
    <div class="hidden sm:flex" :style="{ paddingLeft: '200px' }">
      <div
        v-for="(d, i) in days"
        :key="i"
        class="text-muted-foreground flex-1 text-center text-[10px] font-medium"
      >
        <div class="uppercase tracking-wider">
          {{ d.toLocaleDateString(locale, { weekday: 'short' }) }}
        </div>
        <div class="text-foreground text-[13px] font-semibold">{{ d.getDate() }}</div>
      </div>
    </div>

    <!-- Day header row (mobile) -->
    <div class="flex pl-[88px] sm:hidden">
      <div
        v-for="(d, i) in days"
        :key="i"
        class="text-muted-foreground flex-1 text-center text-[8px] font-semibold"
      >
        {{ d.getDate() }}
      </div>
    </div>

    <!-- Members -->
    <div class="space-y-1">
      <div
        v-for="m in sortedMembers"
        :key="m.id"
        class="flex items-center"
        :class="m.user_id === currentUserId ? 'bg-primary/10 -mx-1 rounded-md px-1 py-1' : 'py-1'"
      >
        <!-- desktop label -->
        <div class="hidden w-[200px] items-center gap-2.5 pr-3 sm:flex">
          <Avatar class="size-7 shrink-0">
            <AvatarImage v-if="false" src="" />
            <AvatarFallback class="bg-muted text-foreground text-[10px] font-semibold">
              {{ memberInitials(m) }}
            </AvatarFallback>
          </Avatar>
          <div class="min-w-0">
            <div
              class="truncate text-[13px] leading-tight"
              :class="m.user_id === currentUserId ? 'font-semibold' : 'font-medium'"
            >
              {{ m.user_full_name ?? m.user_email ?? '—' }}
              <span
                v-if="m.user_id === currentUserId"
                class="text-primary ml-1 text-[10px] font-semibold"
              >
                {{ t('duties.availability.youSuffix') }}
              </span>
            </div>
            <div class="text-muted-foreground truncate text-[10px]">
              {{ m.user_email ?? '' }}
            </div>
          </div>
        </div>

        <!-- mobile label -->
        <div class="flex w-[88px] shrink-0 items-center gap-1.5 sm:hidden">
          <Avatar class="size-5 shrink-0">
            <AvatarImage v-if="false" src="" />
            <AvatarFallback class="bg-muted text-foreground text-[9px] font-semibold">
              {{ memberInitials(m) }}
            </AvatarFallback>
          </Avatar>
          <span
            class="text-foreground truncate text-[11px]"
            :class="m.user_id === currentUserId ? 'font-semibold' : 'font-medium'"
          >
            {{ memberDisplayShort(m) }}
          </span>
        </div>

        <div class="flex flex-1 gap-0.5 sm:gap-1">
          <!-- Hover a cell to see its date. -->
          <HintTooltip v-for="(d, di) in days" :key="di" :label="formatDateLabel(dateKey(d))">
            <div
              class="h-[18px] flex-1 rounded-sm sm:h-[22px]"
              :class="heatStyles[heatFor(m, di)]"
            />
          </HintTooltip>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="text-muted-foreground flex items-center justify-center gap-1.5 pt-1 text-[11px]">
      <span>{{ t('duties.availability.heatLegendLow') }}</span>
      <div v-for="(c, i) in heatStyles" :key="i" class="size-3 rounded-sm" :class="c" />
      <span>{{ t('duties.availability.heatLegendFull') }}</span>
    </div>
  </div>
</template>
