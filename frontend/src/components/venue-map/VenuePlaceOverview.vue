<script setup lang="ts">
import { computed } from 'vue'

import { MapPinOff, Star } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { LocationRead } from '@/client/types.gen'
import {
  type PlaceOverviewItem,
  STAFFING_CLASSES,
  staffingLabelKey,
  staffingStatus,
} from '@/lib/venue-map'

/**
 * Every place of the event with that day's staffing, for the map's side panel
 * while nothing is selected (and the "All places" drawer on a phone). The
 * number in each badge is the one on the place's pill. Picking a row emits
 * `select`; the map then shows the place and its details.
 */
const props = defineProps<{
  items: ReadonlyArray<PlaceOverviewItem>
  /** E.g. "Sat, 17 Oct", for the heading. */
  dayLabel: string
}>()

const emit = defineEmits<{
  select: [location: LocationRead]
}>()

const { t } = useI18n()

const rows = computed(() =>
  props.items.map((item) => {
    const status = staffingStatus(item.stat)
    return { ...item, status, classes: STAFFING_CLASSES[status] }
  }),
)

const totals = computed(() =>
  props.items.reduce(
    (sum, item) => ({
      booked: sum.booked + (item.stat?.booked ?? 0),
      capacity: sum.capacity + (item.stat?.capacity ?? 0),
    }),
    { booked: 0, capacity: 0 },
  ),
)
</script>

<template>
  <div class="space-y-3" data-testid="map-overview">
    <div class="space-y-1">
      <p class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {{ t('venueMap.panel.overviewOn', { day: dayLabel }) }}
      </p>
      <h2
        class="text-xl leading-tight font-semibold tracking-tight outline-none"
        tabindex="-1"
        data-testid="map-overview-title"
      >
        {{ t('venueMap.panel.overviewTitle') }}
      </h2>
      <p v-if="totals.capacity > 0" class="text-muted-foreground text-sm">
        {{ t('venueMap.panel.overviewTotal', totals) }}
      </p>
    </div>

    <p v-if="items.length === 0" class="text-muted-foreground py-4 text-sm">
      {{ t('venueMap.panel.noPlaces') }}
    </p>

    <ul v-else class="space-y-1">
      <li v-for="row in rows" :key="row.location.id">
        <button
          type="button"
          class="hover:bg-muted/60 focus-visible:ring-ring/50 flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left outline-none focus-visible:ring-[3px]"
          :data-testid="`map-overview-${row.location.id}`"
          @click="emit('select', row.location)"
        >
          <span
            class="text-staff-foreground flex size-[22px] shrink-0 items-center justify-center rounded-full text-[11px] font-bold tabular-nums"
            :class="row.classes.bg"
            aria-hidden="true"
          >
            {{ row.badge }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-1.5">
              <span class="truncate text-sm font-medium">{{ row.location.name }}</span>
              <template v-if="row.mine">
                <Star class="text-primary size-3.5 shrink-0 fill-current" aria-hidden="true" />
                <span class="sr-only">{{ t('venueMap.panel.mine') }}</span>
              </template>
              <template v-if="!row.pinned">
                <MapPinOff class="text-muted-foreground size-3.5 shrink-0" aria-hidden="true" />
                <span class="sr-only">{{ t('venueMap.panel.notOnMap') }}</span>
              </template>
            </span>
            <span class="text-foreground/75 block truncate text-[13px]">
              {{ t(staffingLabelKey(row.status)) }}
            </span>
          </span>
          <span
            v-if="row.stat && row.stat.capacity > 0"
            class="shrink-0 rounded-full border px-2 py-0.5 text-[13px] font-semibold tabular-nums"
            :class="row.classes.chip"
          >
            {{ row.stat.booked }}/{{ row.stat.capacity }}
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>
