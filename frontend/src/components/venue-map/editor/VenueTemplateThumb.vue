<script setup lang="ts">
import { computed, ref } from 'vue'

import { ImageOff, Map as MapIcon } from '@lucide/vue'
import { useElementSize } from '@vueuse/core'

import { useAuthedImage } from '@/composables/useAuthedImage'
import { useTemplateShapes } from '@/composables/useVenueTemplates'

import { Skeleton } from '@/components/ui/skeleton'

import VenueShapeLayer from '@/components/venue-map/VenueShapeLayer.vue'

import type { VenueTemplateSummary } from '@/client/types.gen'
import { templateImageUrl, unitsPerPixel } from '@/lib/venue-map'
import { planSize, planSurfaceClass, templateRenderShapes } from '@/lib/venue-shapes'

/**
 * A small preview of a venue template: its picture (if any) with its drawing
 * on top, fitted into the box at the template's own aspect. Decorative — the
 * card around it carries the name.
 */
const props = defineProps<{
  template: VenueTemplateSummary
}>()

const size = computed(() => planSize(props.template))
const width = computed(() => size.value.W)
const height = computed(() => size.value.H)

const svgRef = ref<SVGSVGElement | null>(null)
const { width: clientWidth, height: clientHeight } = useElementSize(svgRef)
const scale = computed(() =>
  unitsPerPixel(
    { x: 0, y: 0, w: width.value, h: height.value },
    clientWidth.value,
    clientHeight.value,
  ),
)

const { shapes: rawShapes, loading: shapesLoading } = useTemplateShapes(
  () => props.template.id,
  () => (props.template.shape_count ?? 0) > 0,
)
const shapes = computed(() => templateRenderShapes(rawShapes.value))

const {
  src,
  loading: imageLoading,
  error: imageError,
} = useAuthedImage(() => templateImageUrl(props.template))

const loading = computed(() => shapesLoading.value || imageLoading.value)
const isEmpty = computed(
  () => !props.template.image_etag && (props.template.shape_count ?? 0) === 0,
)
</script>

<template>
  <div
    class="map-ground relative aspect-[4/3] w-full overflow-hidden rounded-md border p-1.5"
    :class="planSurfaceClass(template)"
    aria-hidden="true"
    data-testid="template-thumb"
  >
    <svg
      ref="svgRef"
      :viewBox="`0 0 ${width} ${height}`"
      preserveAspectRatio="xMidYMid meet"
      class="block h-full w-full"
    >
      <image
        v-if="src"
        :href="src"
        x="0"
        y="0"
        :width="width"
        :height="height"
        preserveAspectRatio="none"
      />
      <rect
        v-else
        x="0"
        y="0"
        :width="width"
        :height="height"
        :style="{ fill: 'var(--map-canvas)', stroke: 'var(--map-canvas-edge)' }"
        stroke-width="1"
        vector-effect="non-scaling-stroke"
      />
      <VenueShapeLayer
        v-if="shapes.length"
        :shapes="shapes"
        :width="width"
        :height="height"
        :units-per-pixel="scale"
        interactive="none"
        :min-label-px="8"
      />
    </svg>
    <Skeleton v-if="loading" class="absolute inset-0 h-full w-full rounded-none" />
    <div
      v-else-if="imageError || isEmpty"
      class="text-muted-foreground absolute inset-0 flex items-center justify-center"
    >
      <ImageOff v-if="imageError" class="size-5" />
      <MapIcon v-else class="size-5" />
    </div>
  </div>
</template>
