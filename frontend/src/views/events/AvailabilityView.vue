<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { Check, ChevronsLeftRight, ChevronsRightLeft, Trash2, Users, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'

import MyAvailabilityCard from '@/components/events/MyAvailabilityCard.vue'
import TeamAvailabilityHeatmap from '@/components/events/TeamAvailabilityHeatmap.vue'

import type {
  UserAvailabilityRead,
  UserAvailabilityWithUser,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

type AvailabilityType = 'fully_available' | 'specific_dates' | 'time_range'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const eventId = computed(() => authStore.selectedEventId ?? null)
const canManage = computed(() =>
  eventId.value ? authStore.canManageEvent(eventId.value) : false,
)
const event = computed(() => authStore.selectedEvent)
const myUserId = computed(() => authStore.profile?.id ?? null)

// === Local edit state ===
const mode = ref<AvailabilityType>('specific_dates')
const dailyFrom = ref(9)
const dailyTo = ref(17)
const dailyExcluded = ref<Set<number>>(new Set())
const avail = ref<Set<string>>(new Set())
const tab = ref<'me' | 'team'>('me')
/** The saved availability is loading (from the first render on, when there is an event). */
const loading = ref(eventId.value !== null)
const showFullDay = ref(false)

const myAvailability = ref<UserAvailabilityRead | null>(null)
const allAvailabilities = ref<UserAvailabilityWithUser[]>([])

// Pydantic dt.time can't represent 24:00:00, but the UI's exclusive end-of-day
// is hour 24. Send 23:59:59 on the wire and round-trip it back to 24.
const END_OF_DAY_WIRE = '23:59:59'
function endHourToWire(endHour: number): string {
  return endHour >= 24 ? END_OF_DAY_WIRE : `${String(endHour).padStart(2, '0')}:00:00`
}
function parseEndHour(timeStr: string): number {
  return timeStr === END_OF_DAY_WIRE ? 24 : parseInt(timeStr.slice(0, 2), 10)
}

// === Date grid derivation ===
const days = computed<Date[]>(() => {
  if (!event.value) return []
  const start = new Date(event.value.start_date + 'T00:00:00')
  const end = new Date(event.value.end_date + 'T00:00:00')
  const out: Date[] = []
  const d = new Date(start)
  while (d <= end) {
    out.push(new Date(d))
    d.setDate(d.getDate() + 1)
  }
  return out
})

// Event-defined window (HH:MM:SS or null). When unset, treated as full-day 0–24.
const eventStartHour = computed(() => {
  const t = event.value?.default_start_time
  return t ? parseInt(t.slice(0, 2), 10) : 0
})
const eventEndHour = computed(() => {
  const t = event.value?.default_end_time
  return t ? parseInt(t.slice(0, 2), 10) : 24
})
const hasEventWindow = computed(
  () => !!event.value?.default_start_time && !!event.value?.default_end_time,
)

// Hour slots shown in the grid. When the event has a window, default to that
// window; otherwise show the full day. The "Show full day" toggle expands
// a windowed grid to all 24 hours (still allows painting outside the window).
const hours = computed(() => {
  if (!hasEventWindow.value || showFullDay.value) {
    return Array.from({ length: 24 }, (_, i) => i)
  }
  const start = eventStartHour.value
  const end = eventEndHour.value
  return Array.from({ length: Math.max(0, end - start) }, (_, i) => i + start)
})

const subtitle = computed(() => {
  if (!event.value) return t('duties.availability.subtitle')
  const opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }
  const start = new Date(event.value.start_date).toLocaleDateString(locale.value, opts)
  const end = new Date(event.value.end_date).toLocaleDateString(locale.value, opts)
  return `${event.value.name} · ${start} – ${end}`
})

// === Hydrate local state from server ===
// If a saved specific_dates payload uses one entry per day with a uniform
// start/end across all dates, we present it as time_range with exclusions —
// that's how it was authored in the new "daily" UI.
function trySpecificAsDaily(
  server: UserAvailabilityRead,
): { from: number; to: number; excluded: Set<number> } | null {
  const entries = server.available_dates ?? []
  if (entries.length === 0) return null
  // Group by date — abort if any date has multiple entries
  const byDate = new Map<string, { start_time?: string | null; end_time?: string | null }>()
  for (const e of entries) {
    if (byDate.has(e.slot_date)) return null
    byDate.set(e.slot_date, e)
  }
  // All entries must share the same explicit start/end (full-day entries → not daily)
  const sample = entries[0]
  if (!sample.start_time || !sample.end_time) return null
  for (const e of entries) {
    if (e.start_time !== sample.start_time || e.end_time !== sample.end_time) return null
  }
  const excluded = new Set<number>()
  for (let di = 0; di < days.value.length; di += 1) {
    const k = days.value[di].toISOString().slice(0, 10)
    if (!byDate.has(k)) excluded.add(di)
  }
  return {
    from: parseInt(sample.start_time.slice(0, 2), 10),
    to: parseEndHour(sample.end_time),
    excluded,
  }
}

function hydrateFromServer(server: UserAvailabilityRead | null) {
  if (!server) {
    mode.value = 'specific_dates'
    avail.value = new Set()
    dailyExcluded.value = new Set()
    // Seed the daily-window slider from the event window when available so
    // the user starts inside the window the organizer set.
    dailyFrom.value = hasEventWindow.value ? eventStartHour.value : 9
    dailyTo.value = hasEventWindow.value ? eventEndHour.value : 17
    return
  }

  if (server.availability_type === 'time_range') {
    mode.value = 'time_range'
    if (server.default_start_time) dailyFrom.value = parseInt(server.default_start_time.slice(0, 2), 10)
    if (server.default_end_time) dailyTo.value = parseEndHour(server.default_end_time)
    dailyExcluded.value = new Set()
    avail.value = new Set()
    return
  }

  if (server.availability_type === 'fully_available') {
    mode.value = 'fully_available'
    dailyExcluded.value = new Set()
    avail.value = new Set()
    return
  }

  // specific_dates: try interpreting as daily-with-exclusions; else fall back to painter
  const asDaily = trySpecificAsDaily(server)
  if (asDaily) {
    mode.value = 'time_range'
    dailyFrom.value = asDaily.from
    dailyTo.value = asDaily.to
    dailyExcluded.value = asDaily.excluded
    avail.value = new Set()
    return
  }

  mode.value = 'specific_dates'
  dailyExcluded.value = new Set()
  const newAvail = new Set<string>()
  for (const e of server.available_dates ?? []) {
    const di = days.value.findIndex((d) => d.toISOString().slice(0, 10) === e.slot_date)
    if (di < 0) continue
    const start = e.start_time ? parseInt(e.start_time.slice(0, 2), 10) : hours.value[0]
    const end = e.end_time
      ? parseEndHour(e.end_time)
      : hours.value[hours.value.length - 1] + 1
    for (let h = start; h < end; h += 1) {
      if (hours.value.includes(h)) newAvail.add(`${di}-${h}`)
    }
  }
  avail.value = newAvail
}

// === Dirty tracking (compare current edit state to last loaded server payload) ===
const baselineKey = ref<string>('')
function snapshotKey(): string {
  if (mode.value === 'fully_available') return 'full'
  if (mode.value === 'time_range') {
    const ex = [...dailyExcluded.value].sort((a, b) => a - b).join(',')
    return `range:${dailyFrom.value}-${dailyTo.value}:${ex}`
  }
  return `specific:${[...avail.value].sort().join(',')}`
}
const isDirty = computed(() => snapshotKey() !== baselineKey.value)

async function loadData() {
  if (!eventId.value) return
  // Until the saved availability is in, the editor takes no input: hydrating
  // would overwrite a mode picked in the meantime and leave nothing to save.
  loading.value = true
  try {
    try {
      const res = await get<{ data: UserAvailabilityRead }>({
        url: `/events/${eventId.value}/availability/me`,
      })
      myAvailability.value = res.data
    } catch {
      myAvailability.value = null
    }
    hydrateFromServer(myAvailability.value)
    baselineKey.value = snapshotKey()
    loading.value = false

    if (canManage.value) {
      try {
        const res = await get<{ data: UserAvailabilityWithUser[] }>({
          url: `/events/${eventId.value}/availabilities`,
        })
        allAvailabilities.value = res.data
      } catch {
        allAvailabilities.value = []
      }
    }
  } finally {
    loading.value = false
  }
}

// === Build payload from local state ===
function buildPayload() {
  const baseDates: { date: string; start_time?: string; end_time?: string }[] = []

  // Daily window with some days disabled → persist as specific_dates so the
  // backend records exactly which days the user is unavailable.
  if (mode.value === 'time_range' && dailyExcluded.value.size > 0) {
    const startStr = `${String(dailyFrom.value).padStart(2, '0')}:00:00`
    const endStr = endHourToWire(dailyTo.value)
    for (let di = 0; di < days.value.length; di += 1) {
      if (dailyExcluded.value.has(di)) continue
      baseDates.push({
        date: days.value[di].toISOString().slice(0, 10),
        start_time: startStr,
        end_time: endStr,
      })
    }
    return {
      availability_type: 'specific_dates' as const,
      default_start_time: undefined,
      default_end_time: undefined,
      dates: baseDates,
    }
  }

  if (mode.value === 'specific_dates') {
    for (let di = 0; di < days.value.length; di += 1) {
      const dayDate = days.value[di]
      const dayHours = hours.value
        .filter((h) => avail.value.has(`${di}-${h}`))
        .sort((a, b) => a - b)
      if (dayHours.length === 0) continue

      // Group consecutive runs into [start, end+1) ranges
      const runs: [number, number][] = []
      let runStart = dayHours[0]
      let runPrev = dayHours[0]
      for (let i = 1; i < dayHours.length; i += 1) {
        const h = dayHours[i]
        if (h === runPrev + 1) {
          runPrev = h
        } else {
          runs.push([runStart, runPrev + 1])
          runStart = h
          runPrev = h
        }
      }
      runs.push([runStart, runPrev + 1])

      const dateStr = dayDate.toISOString().slice(0, 10)
      const fullDay = runs.length === 1 && runs[0][0] === hours.value[0] && runs[0][1] === hours.value[hours.value.length - 1] + 1
      if (fullDay) {
        baseDates.push({ date: dateStr })
      } else {
        for (const [s, e] of runs) {
          baseDates.push({
            date: dateStr,
            start_time: `${String(s).padStart(2, '0')}:00:00`,
            end_time: endHourToWire(e),
          })
        }
      }
    }
  }

  return {
    availability_type: mode.value,
    default_start_time:
      mode.value === 'time_range'
        ? `${String(dailyFrom.value).padStart(2, '0')}:00:00`
        : undefined,
    default_end_time:
      mode.value === 'time_range' ? endHourToWire(dailyTo.value) : undefined,
    dates: baseDates,
  }
}

async function saveChanges() {
  if (!eventId.value) return
  try {
    const res = await post<{ data: UserAvailabilityRead }>({
      url: `/events/${eventId.value}/availability`,
      body: buildPayload(),
    })
    myAvailability.value = res.data
    hydrateFromServer(res.data)
    baselineKey.value = snapshotKey()
    toast.success(t('duties.availability.update'))
    if (canManage.value) await loadData()
  } catch (error) {
    toastApiError(error)
  }
}

async function clearAll() {
  if (mode.value === 'specific_dates') {
    avail.value = new Set()
    return
  }
  if (mode.value === 'time_range') {
    dailyFrom.value = 9
    dailyTo.value = 17
    dailyExcluded.value = new Set()
    return
  }
}

async function removeAvailability() {
  if (!eventId.value) return
  const confirmed = await confirmDestructive(t('duties.availability.removeConfirm'))
  if (!confirmed) return
  try {
    await del({ url: `/events/${eventId.value}/availability/me` })
    myAvailability.value = null
    hydrateFromServer(null)
    baselineKey.value = snapshotKey()
    toast.success(t('duties.availability.remove'))
    if (canManage.value) await loadData()
  } catch (error) {
    toastApiError(error)
  }
}

watch(eventId, loadData)
onMounted(loadData)

// Self entry shown in team heatmap (synthesized from edit state if user hasn't saved yet)
const teamMembers = computed<UserAvailabilityWithUser[]>(() => {
  if (!myUserId.value) return allAvailabilities.value
  const hasSelf = allAvailabilities.value.some((m) => m.user_id === myUserId.value)
  if (hasSelf || !myAvailability.value) return allAvailabilities.value
  // include myself when admin can't see (non-manager flow only shows admin list when canManage)
  return allAvailabilities.value
})
</script>

<template>
  <div data-testid="availability-view" class="mx-auto w-full max-w-6xl space-y-4">
    <!-- Title + actions -->
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 space-y-2">
        <h1
          data-testid="page-heading"
          class="text-2xl sm:text-3xl font-bold tracking-tight"
        >
          {{ t('duties.availability.title') }}
        </h1>
        <p class="text-muted-foreground">{{ subtitle }}</p>
      </div>
      <div class="flex shrink-0 gap-2">
        <Button
          v-if="myAvailability"
          variant="ghost"
          size="sm"
          data-testid="btn-remove-availability"
          class="text-destructive"
          @click="removeAvailability"
        >
          <Trash2 class="size-4 sm:mr-1.5" />
          <span class="hidden sm:inline">{{ t('duties.availability.remove') }}</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          :disabled="!isDirty"
          data-testid="btn-clear-all"
          @click="clearAll"
        >
          <X class="size-4 sm:mr-1.5" />
          <span class="hidden sm:inline">{{ t('duties.availability.clearAll') }}</span>
        </Button>
        <Button
          size="sm"
          :disabled="!isDirty"
          data-testid="btn-save"
          @click="saveChanges"
        >
          <Check class="size-4 sm:mr-1.5" />
          <span class="hidden sm:inline">{{ t('duties.availability.saveChanges') }}</span>
        </Button>
      </div>
    </div>

    <Badge v-if="isDirty" variant="secondary" class="sm:hidden">
      {{ t('duties.availability.unsavedHint') }}
    </Badge>

    <!-- Mobile tab toggle (desktop shows both stacked) -->
    <div v-if="canManage" class="md:hidden">
      <div class="bg-muted/60 flex rounded-lg p-1">
        <button
          v-for="(tabKey, idx) in (['me', 'team'] as const)"
          :key="tabKey"
          class="flex-1 rounded-md py-1.5 text-[12px] font-semibold transition-colors"
          :class="
            tab === tabKey
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground'
          "
          :data-testid="`tab-${tabKey}`"
          @click="tab = tabKey"
        >
          {{
            idx === 0
              ? t('duties.availability.meTab')
              : t('duties.availability.teamTab', { count: allAvailabilities.length })
          }}
        </button>
      </div>
    </div>

    <!-- My availability card — visible always on desktop; hidden on mobile when team tab active -->
    <Card
      data-testid="section-my-availability"
      class="overflow-hidden"
      :class="canManage && tab === 'team' ? 'hidden md:block' : ''"
      :aria-busy="loading || undefined"
    >
      <CardContent class="p-4 sm:p-5">
        <div
          v-if="hasEventWindow && mode === 'specific_dates'"
          class="mb-3 flex justify-end"
        >
          <Button
            variant="ghost"
            size="sm"
            data-testid="btn-toggle-full-day"
            @click="showFullDay = !showFullDay"
          >
            <component
              :is="showFullDay ? ChevronsRightLeft : ChevronsLeftRight"
              class="size-4 sm:mr-1.5"
            />
            <span class="hidden sm:inline">
              {{
                showFullDay
                  ? t('duties.availability.collapseToEventHours')
                  : t('duties.availability.showOutsideEventHours')
              }}
            </span>
          </Button>
        </div>
        <MyAvailabilityCard
          v-model:mode="mode"
          v-model:avail="avail"
          v-model:dailyFrom="dailyFrom"
          v-model:dailyTo="dailyTo"
          v-model:dailyExcluded="dailyExcluded"
          :days="days"
          :hours="hours"
          :disabled="loading"
        />
      </CardContent>
    </Card>

    <!-- Team availability card (managers only) — hidden on mobile when me tab active -->
    <Card
      v-if="canManage"
      data-testid="section-admin-availabilities"
      :class="tab === 'me' ? 'hidden md:block' : ''"
    >
      <CardContent class="p-4 sm:p-5">
        <div class="space-y-3">
          <div class="flex items-center gap-2.5">
            <Users class="text-muted-foreground size-5" />
            <h2 class="text-base font-semibold tracking-tight">
              {{ t('duties.availability.teamTitle') }}
            </h2>
            <Badge variant="outline">
              {{ allAvailabilities.length }} {{ t('duties.availability.people') }}
            </Badge>
          </div>

          <p
            v-if="allAvailabilities.length === 0"
            class="text-muted-foreground text-sm"
          >
            {{ t('duties.availability.teamEmpty') }}
          </p>

          <TeamAvailabilityHeatmap
            v-else
            :days="days"
            :hours="hours"
            :members="teamMembers"
            :current-user-id="myUserId"
            :self-mode="mode"
            :self-paint="avail"
            :self-daily-from="dailyFrom"
            :self-daily-to="dailyTo"
            :self-daily-excluded="dailyExcluded"
          />
        </div>
      </CardContent>
    </Card>
  </div>
</template>
