<script setup lang="ts">
import { computed, ref } from 'vue'

import { ImageOff, Map as MapIcon } from '@lucide/vue'
import { until, useElementSize } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useAuthedImage } from '@/composables/useAuthedImage'

import { Skeleton } from '@/components/ui/skeleton'

import VenueMarkerGlyph from '@/components/venue-map/VenueMarkerGlyph.vue'

import type { LocationPin } from '@/client/types.gen'
import { cropAround, planImageUrl, unitsPerPixel, viewBoxToString } from '@/lib/venue-map'

/**
 * A small, fixed 16:9 crop of a venue plan around one location's pin — "this
 * is where your shift is". No pan or zoom.
 *
 * With `linkToMap` the whole box links to the full map, focused on the plan
 * and (given `locationId`) the location. `static` is for print: no link, no
 * hover affordances. Parents await the exposed `ready()` before printing.
 */
const props = withDefaults(
  defineProps<{
    eventId: string
    pin: LocationPin
    /** Adds `?location=` to the map link so the map opens that location. */
    locationId?: string | null
    linkToMap?: boolean
    static?: boolean
  }>(),
  { locationId: null, linkToMap: true, static: false },
)

const { t } = useI18n()

const isStatic = computed(() => props.static)
const asLink = computed(() => props.linkToMap && !isStatic.value)

const width = computed(() => props.pin.image_width ?? 0)
const height = computed(() => props.pin.image_height ?? 0)

const viewBox = computed(() => cropAround(props.pin.x, props.pin.y, width.value, height.value))

const svgRef = ref<SVGSVGElement | null>(null)
const { width: clientWidth, height: clientHeight } = useElementSize(svgRef)
const scale = computed(() => unitsPerPixel(viewBox.value, clientWidth.value, clientHeight.value))

const image = useAuthedImage(() =>
  planImageUrl({ id: props.pin.plan_id, image_etag: props.pin.image_etag }),
)
const { src, loading, error } = image

const decodedSrc = ref<string | null>(null)
const markDecoded = () => (decodedSrc.value = src.value)

const mapRoute = computed(() => ({
  name: 'event-map',
  params: { eventId: props.eventId },
  query: {
    plan: props.pin.plan_id,
    ...(props.locationId ? { location: props.locationId } : {}),
  },
}))

const label = computed(() => t('venueMap.miniMap.alt', { plan: props.pin.plan_name }))

/** Resolves once the picture has been fetched and drawn, or has failed. */
async function ready() {
  await image.ready()
  if (!src.value) return
  await until(() => decodedSrc.value === src.value || !!error.value).toBe(true, {
    timeout: 5000,
  })
}

defineExpose({ ready })
</script>

<template>
  <component
    :is="asLink ? RouterLink : 'div'"
    v-bind="
      asLink ? { to: mapRoute, 'aria-label': `${label} – ${t('venueMap.miniMap.open')}` } : {}
    "
    class="venue-mini-map bg-muted/40 group relative block aspect-[16/9] w-full overflow-hidden rounded-lg border"
    :class="asLink ? 'focus-visible:ring-ring/50 outline-none focus-visible:ring-[3px]' : ''"
    data-testid="venue-mini-map"
  >
    <svg
      ref="svgRef"
      :viewBox="viewBoxToString(viewBox)"
      class="block h-full w-full"
      role="img"
      :aria-label="label"
    >
      <image
        v-if="src"
        :href="src"
        x="0"
        y="0"
        :width="width"
        :height="height"
        preserveAspectRatio="none"
        @load="markDecoded"
        @error="markDecoded"
      />
      <VenueMarkerGlyph
        kind="location"
        :x="pin.x * width"
        :y="pin.y * height"
        :scale="scale"
        highlighted
        aria-hidden="true"
      />
    </svg>

    <Skeleton v-if="loading" class="absolute inset-0 h-full w-full rounded-none" />
    <div
      v-else-if="error"
      class="text-muted-foreground absolute inset-0 flex items-center justify-center"
    >
      <ImageOff class="size-5" />
      <span class="sr-only">{{ t('venueMap.canvas.error') }}</span>
    </div>

    <span
      v-if="asLink"
      class="bg-background/90 text-foreground absolute right-2 bottom-2 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium shadow-sm transition-colors group-hover:bg-background"
      aria-hidden="true"
    >
      <MapIcon class="size-3.5" />
      {{ t('venueMap.miniMap.open') }}
    </span>
    <span
      v-else
      class="bg-background/90 text-muted-foreground absolute bottom-2 left-2 rounded-md px-2 py-0.5 text-xs"
    >
      {{ pin.plan_name }}
    </span>
  </component>
</template>

<style scoped>
@media print {
  .venue-mini-map {
    break-inside: avoid;
  }
}
</style>
