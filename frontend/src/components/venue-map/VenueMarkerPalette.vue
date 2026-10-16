<script setup lang="ts">
import { computed } from 'vue'

import { CheckCircle2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { LocationRead } from '@/client/types.gen'
import {
  GENERIC_MARKER_KINDS,
  type MarkerKind,
  markerIcon,
  markerKindLabelKey,
} from '@/lib/venue-map'

/**
 * What the map editor can pin on the current plan: the event's locations that
 * are not on it yet, then the generic points (entrance, first aid, …), which
 * may appear any number of times.
 *
 * Picking an item starts placement mode in the editor; `active` is the key of
 * the item being placed (`location:<id>` or `kind:<kind>`), shown as pressed.
 */
const props = withDefaults(
  defineProps<{
    /** Every location of the event. */
    locations: ReadonlyArray<LocationRead>
    /** Location ids that already have a pin on this plan. */
    placedLocationIds: ReadonlyArray<string>
    active?: string | null
    disabled?: boolean
  }>(),
  { active: null, disabled: false },
)

const emit = defineEmits<{
  'pick-location': [location: LocationRead]
  'pick-kind': [kind: Exclude<MarkerKind, 'location'>]
}>()

const { t } = useI18n()

const unplaced = computed(() => {
  const placed = new Set(props.placedLocationIds)
  return props.locations.filter((location) => !placed.has(location.id))
})

const locationIcon = markerIcon('location')

const itemClass =
  'flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors ' +
  'hover:bg-accent focus-visible:ring-ring/50 outline-none focus-visible:ring-[3px] ' +
  'disabled:pointer-events-none disabled:opacity-50 aria-pressed:border-primary aria-pressed:bg-primary/10'
</script>

<template>
  <div class="space-y-4" data-testid="marker-palette">
    <div class="space-y-1">
      <h3 class="text-sm font-semibold">{{ t('mapEditor.palette.title') }}</h3>
      <p class="text-muted-foreground text-xs">{{ t('mapEditor.palette.hint') }}</p>
    </div>

    <section class="space-y-2">
      <h4 class="text-muted-foreground text-xs font-medium uppercase tracking-wide">
        {{ t('mapEditor.palette.locations') }}
        <span v-if="unplaced.length > 0" class="normal-case tracking-normal">
          · {{ t('mapEditor.palette.unplaced') }}
        </span>
      </h4>
      <p v-if="locations.length === 0" class="text-muted-foreground text-sm">
        {{ t('mapEditor.palette.noLocations') }}
      </p>
      <p
        v-else-if="unplaced.length === 0"
        class="text-muted-foreground flex items-center gap-2 text-sm"
      >
        <CheckCircle2 class="size-4 text-emerald-600" aria-hidden="true" />
        {{ t('mapEditor.palette.allPlaced') }}
      </p>
      <!-- In the editor's phone sheet the sheet scrolls; no box scrolling inside it. -->
      <ul
        v-else
        class="grid grid-cols-1 gap-1.5 lg:max-h-80 lg:overflow-y-auto"
        data-testid="palette-locations"
      >
        <li v-for="location in unplaced" :key="location.id">
          <button
            type="button"
            :class="itemClass"
            :aria-pressed="active === `location:${location.id}`"
            :disabled="disabled"
            :data-testid="`palette-location-${location.id}`"
            @click="emit('pick-location', location)"
          >
            <component :is="locationIcon" class="text-primary size-4 shrink-0" aria-hidden="true" />
            <span class="min-w-0 truncate">{{ location.name }}</span>
          </button>
        </li>
      </ul>
    </section>

    <section class="space-y-2">
      <h4 class="text-muted-foreground text-xs font-medium uppercase tracking-wide">
        {{ t('mapEditor.palette.generic') }}
      </h4>
      <ul class="grid grid-cols-2 gap-1.5">
        <li v-for="kind in GENERIC_MARKER_KINDS" :key="kind">
          <button
            type="button"
            :class="itemClass"
            :aria-pressed="active === `kind:${kind}`"
            :disabled="disabled"
            :data-testid="`palette-kind-${kind}`"
            @click="emit('pick-kind', kind)"
          >
            <component :is="markerIcon(kind)" class="size-4 shrink-0" aria-hidden="true" />
            <span class="min-w-0 truncate">{{ t(markerKindLabelKey(kind)) }}</span>
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
