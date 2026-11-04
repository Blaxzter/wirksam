<script setup lang="ts">
import { computed } from 'vue'

import { Mail, Phone, Plus } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

import type { ShiftBookingEntry } from '@/client/types.gen'
import { initials, telHref } from '@/lib/format'
import { parseServerDate } from '@/lib/server-time'

/**
 * "Signed up" in the shift dialog: how full the shift is, who is on it and how
 * to reach them.
 *
 * E-mail, phone and the note left for the organisers arrive only for the
 * task's organisers and people in charge (and on the viewer's own row): the
 * server leaves them out for everyone else, so a volunteer sees names and
 * dates only. Nobody is offered a button to call or write to themselves.
 *
 * `compact` is the phone sheet: a list with a call and an e-mail button per
 * person, at thumb size. Otherwise a table with the contact details written
 * out, since a desktop has no dialler to hand them to.
 */
const props = defineProps<{
  bookings: ShiftBookingEntry[]
  /** `max_bookings` — how many people the shift is asking for. */
  capacity: number
  loading?: boolean
  /**
   * How many the shift itself says are on it (`current_bookings`): the count
   * and bar show this while the list is still loading, instead of "0 of 3".
   */
  booked?: number | null
  /** The shift is over: free places can no longer be filled, so say nothing of them. */
  hideFree?: boolean
  /** Phone layout. */
  compact?: boolean
  /** The viewer's own user id, to mark their row. */
  myId?: string | null
}>()

const { t, locale } = useI18n()

const taken = computed(() =>
  props.loading && props.booked != null ? props.booked : props.bookings.length,
)
const full = computed(() => taken.value >= props.capacity)
const fill = computed(() =>
  props.capacity > 0 ? Math.min(100, Math.round((taken.value / props.capacity) * 100)) : 0,
)

/**
 * One summary row rather than one row per empty place: a shift asking for
 * twelve people would otherwise push everyone who actually signed up off the
 * screen behind eleven identical placeholders.
 */
const freeCount = computed(() => (props.hideFree ? 0 : Math.max(0, props.capacity - taken.value)))

const countText = computed(() =>
  // The table has room to say what is left; the phone header says it in the list.
  !props.compact && freeCount.value > 0
    ? t(
        'duties.shifts.roster.countFree',
        { taken: taken.value, max: props.capacity, n: freeCount.value },
        freeCount.value,
      )
    : t('duties.shifts.roster.count', { taken: taken.value, max: props.capacity }),
)

const isMe = (entry: ShiftBookingEntry) => !!props.myId && entry.user_id === props.myId

const nameOf = (entry: ShiftBookingEntry) => entry.user_name || entry.user_email || '?'

/** "2 July", the year only when it isn't this one. The server sends naive UTC. */
function sinceDate(entry: ShiftBookingEntry): string {
  const d = parseServerDate(entry.created_at)
  if (!d) return ''
  const options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long' }
  if (d.getFullYear() !== new Date().getFullYear()) options.year = 'numeric'
  return d.toLocaleDateString(locale.value, options)
}

const tel = (entry: ShiftBookingEntry) => (isMe(entry) ? null : telHref(entry.user_phone_number))
const mailto = (entry: ShiftBookingEntry) =>
  !isMe(entry) && entry.user_email ? `mailto:${entry.user_email}` : null

/** The phone line under a name: when they signed up, and what's missing to reach them. */
function subline(entry: ShiftBookingEntry): string {
  const parts = [t('duties.shifts.roster.since', { date: sinceDate(entry) })]
  if (!isMe(entry)) {
    // A number the dialler can't use is still worth reading out.
    if (entry.user_phone_number && !telHref(entry.user_phone_number)) {
      parts.push(entry.user_phone_number)
    } else if (entry.user_email && !entry.user_phone_number) {
      // Contact details came, but there is no number among them.
      parts.push(t('duties.shifts.roster.noNumber'))
    }
  }
  return parts.join(' · ')
}

/** The table's contact column only earns its width when someone in it can be reached. */
const showContact = computed(() =>
  props.bookings.some((b) => !isMe(b) && (b.user_email || b.user_phone_number)),
)
const gridClass = computed(() =>
  showContact.value
    ? 'grid-cols-[minmax(0,1fr)_200px_84px]'
    : 'grid-cols-[minmax(0,1fr)_minmax(84px,auto)]',
)

const entryAvatarUrl = (entry: ShiftBookingEntry): string | null =>
  avatarUrlFor({ id: entry.user_id, avatar_etag: entry.user_avatar_etag ?? null })
</script>

<template>
  <section
    data-testid="shift-roster"
    aria-labelledby="shift-roster-title"
    class="flex flex-col"
    :class="compact ? 'gap-2' : 'gap-2.5'"
  >
    <div class="flex items-center justify-between gap-2">
      <h3 id="shift-roster-title" class="text-[17px] font-bold">
        {{ t('duties.shifts.roster.title') }}
      </h3>
      <span
        class="flex items-center gap-2 text-[13px] text-muted-foreground tabular-nums"
        data-testid="shift-roster-count"
      >
        <span
          aria-hidden="true"
          class="block h-1.5 overflow-hidden rounded-full bg-muted"
          :class="compact ? 'w-[60px]' : 'w-[72px]'"
        >
          <span
            class="block h-full rounded-full"
            :class="full ? 'bg-primary' : 'bg-staff-partial'"
            :style="{ width: `${fill}%` }"
          />
        </span>
        {{ countText }}
      </span>
    </div>

    <p v-if="loading" class="py-2 text-sm text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>

    <p
      v-else-if="bookings.length === 0 && freeCount === 0"
      class="py-2 text-sm text-muted-foreground"
      data-testid="shift-roster-nobody"
    >
      {{ t('duties.shifts.roster.nobody') }}
    </p>

    <!-- Phone: one row per person, the ways to reach them as buttons -->
    <ul
      v-else-if="compact"
      class="divide-y divide-border/70 rounded-2xl border bg-card"
      :aria-label="t('duties.shifts.roster.tableLabel')"
    >
      <li
        v-for="entry in bookings"
        :key="entry.id"
        class="flex flex-col gap-2 py-3 pr-2 pl-3.5"
        data-testid="shift-roster-entry"
      >
        <div class="flex min-w-0 items-center gap-3">
          <Avatar class="size-10 shrink-0">
            <AvatarImage v-if="entryAvatarUrl(entry)" :src="entryAvatarUrl(entry)!" alt="" />
            <AvatarFallback
              class="text-sm font-bold"
              :class="
                isMe(entry) ? 'bg-primary/15 text-primary' : 'bg-accent text-accent-foreground'
              "
            >
              {{ initials(nameOf(entry)) }}
            </AvatarFallback>
          </Avatar>
          <div class="min-w-0 flex-1">
            <p class="flex min-w-0 items-center gap-2">
              <span class="truncate text-base font-semibold">{{ nameOf(entry) }}</span>
              <span
                v-if="isMe(entry)"
                class="shrink-0 rounded-full bg-primary/12 px-2 py-px text-xs font-bold text-primary"
              >
                {{ t('duties.shifts.roster.you') }}
              </span>
            </p>
            <p class="truncate text-[13px] text-muted-foreground">{{ subline(entry) }}</p>
          </div>
          <a
            v-if="tel(entry)"
            :href="tel(entry)!"
            :aria-label="t('duties.shifts.roster.call', { name: nameOf(entry) })"
            class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary outline-none hover:bg-primary/20 focus-visible:ring-[3px] focus-visible:ring-ring/50"
            data-testid="shift-roster-phone"
          >
            <Phone class="size-[18px]" aria-hidden="true" />
          </a>
          <a
            v-if="mailto(entry)"
            :href="mailto(entry)!"
            :aria-label="t('duties.shifts.roster.email', { name: nameOf(entry) })"
            class="flex size-11 shrink-0 items-center justify-center rounded-xl text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
            data-testid="shift-roster-email"
          >
            <Mail class="size-[18px]" aria-hidden="true" />
          </a>
        </div>
        <p
          v-if="entry.notes"
          class="mr-1.5 ml-[52px] rounded-[4px_12px_12px_12px] bg-muted/60 px-3 py-2 text-sm break-words text-foreground/90"
          data-testid="shift-roster-note"
        >
          {{ entry.notes }}
        </p>
      </li>

      <li
        v-if="freeCount > 0"
        class="flex items-center gap-3 px-3.5 py-3"
        data-testid="shift-roster-free"
      >
        <span
          class="flex size-10 shrink-0 items-center justify-center rounded-full border-[1.5px] border-dashed border-muted-foreground/50 text-muted-foreground"
          aria-hidden="true"
        >
          <Plus class="size-[18px]" />
        </span>
        <p class="text-[15px] text-muted-foreground">
          {{ t('duties.shifts.roster.free', { n: freeCount }, freeCount) }}
        </p>
      </li>
    </ul>

    <!-- Desktop: who, how to reach them, since when -->
    <div
      v-else
      role="table"
      :aria-label="t('duties.shifts.roster.tableLabel')"
      class="divide-y divide-border/70 overflow-hidden rounded-2xl border bg-card"
    >
      <div
        v-if="bookings.length > 0"
        role="row"
        class="grid gap-3 bg-muted/60 px-4 py-2 text-xs font-bold text-muted-foreground"
        :class="gridClass"
      >
        <span role="columnheader">{{ t('duties.shifts.roster.colPerson') }}</span>
        <span v-if="showContact" role="columnheader">
          {{ t('duties.shifts.roster.colContact') }}
        </span>
        <span role="columnheader" class="text-right">{{ t('duties.shifts.roster.colSince') }}</span>
      </div>

      <div
        v-for="entry in bookings"
        :key="entry.id"
        role="row"
        class="grid gap-3 px-4 py-3.5"
        :class="[gridClass, entry.notes ? 'items-start' : 'items-center']"
        data-testid="shift-roster-entry"
      >
        <div role="cell" class="flex min-w-0 gap-3" :class="entry.notes ? '' : 'items-center'">
          <Avatar class="size-[38px] shrink-0">
            <AvatarImage v-if="entryAvatarUrl(entry)" :src="entryAvatarUrl(entry)!" alt="" />
            <AvatarFallback
              class="text-[13px] font-bold"
              :class="
                isMe(entry) ? 'bg-primary/15 text-primary' : 'bg-accent text-accent-foreground'
              "
            >
              {{ initials(nameOf(entry)) }}
            </AvatarFallback>
          </Avatar>
          <div class="min-w-0">
            <p class="flex min-w-0 items-center gap-2">
              <span class="truncate text-[15px] font-semibold">{{ nameOf(entry) }}</span>
              <span
                v-if="isMe(entry)"
                class="shrink-0 rounded-full bg-primary/12 px-2 py-px text-xs font-bold text-primary"
              >
                {{ t('duties.shifts.roster.you') }}
              </span>
            </p>
            <p
              v-if="entry.notes"
              class="mt-1.5 rounded-[4px_10px_10px_10px] bg-muted/60 px-2.5 py-1.5 text-[13px] break-words text-foreground/90"
              data-testid="shift-roster-note"
            >
              {{ entry.notes }}
            </p>
          </div>
        </div>

        <div v-if="showContact" role="cell" class="flex min-w-0 flex-col gap-0.5 text-[13px]">
          <template v-if="!isMe(entry)">
            <!-- The number as they typed it; the link dials a cleaned-up copy. -->
            <a
              v-if="tel(entry)"
              :href="tel(entry)!"
              class="flex min-h-6 w-fit max-w-full items-center gap-1.5 font-semibold text-primary underline-offset-2 hover:underline"
              data-testid="shift-roster-phone"
            >
              <Phone class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ entry.user_phone_number }}</span>
            </a>
            <span
              v-else-if="entry.user_phone_number"
              class="flex min-h-6 max-w-full items-center gap-1.5 font-semibold"
              data-testid="shift-roster-phone"
            >
              <Phone class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ entry.user_phone_number }}</span>
            </span>
            <a
              v-if="mailto(entry)"
              :href="mailto(entry)!"
              class="flex min-h-6 w-fit max-w-full items-center gap-1.5 text-foreground/80 underline-offset-2 hover:text-foreground hover:underline"
              data-testid="shift-roster-email"
            >
              <Mail class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ entry.user_email }}</span>
            </a>
          </template>
        </div>

        <span role="cell" class="text-right text-[13px] text-muted-foreground tabular-nums">
          {{ sinceDate(entry) }}
        </span>
      </div>

      <div
        v-if="freeCount > 0"
        role="row"
        class="grid items-center gap-3 px-4 py-3"
        :class="gridClass"
        data-testid="shift-roster-free"
      >
        <div role="cell" class="flex items-center gap-3">
          <span
            class="flex size-[38px] shrink-0 items-center justify-center rounded-full border-[1.5px] border-dashed border-muted-foreground/50 text-muted-foreground"
            aria-hidden="true"
          >
            <Plus class="size-4" />
          </span>
          <p class="text-[15px] text-muted-foreground">
            {{ t('duties.shifts.roster.free', { n: freeCount }, freeCount) }}
          </p>
        </div>
        <span v-if="showContact" role="cell" />
        <span role="cell" />
      </div>
    </div>
  </section>
</template>
