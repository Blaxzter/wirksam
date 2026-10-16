<script setup lang="ts">
import { computed, ref } from 'vue'

import { useI18n } from 'vue-i18n'

import HintTooltip from '@/components/utils/HintTooltip.vue'

import {
  LABEL_STYLES,
  PATH_STYLES_FIRST,
  SHAPE_STYLES,
  type ShapeKind,
  type ShapeStyle,
  shapeStyleClass,
  shapeStyleLabelKey,
} from '@/lib/venue-shapes'

/**
 * The look of a shape: one swatch per style, drawn with the same `vs-*`
 * classes as the map, so a swatch shows exactly what the shape will look like
 * in the current theme. A radio group — arrow keys move the choice.
 *
 * A text can not be a wall, a hedge or a fence (their ink is meant for a
 * line, not for the ground), so `kind: 'label'` leaves those out. A line
 * lists its line looks (path, stream, hedge, fence, wall) first.
 */
const props = defineProps<{
  modelValue: ShapeStyle
  kind: ShapeKind
  labelledby?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [style: ShapeStyle]
}>()

const { t } = useI18n()

const styles = computed<readonly ShapeStyle[]>(() => {
  if (props.kind === 'label') return LABEL_STYLES
  if (props.kind === 'path') return PATH_STYLES_FIRST
  return SHAPE_STYLES
})

const buttons = ref<(HTMLButtonElement | null)[]>([])

function setButton(index: number, el: unknown) {
  buttons.value[index] = (el as HTMLButtonElement | null) ?? null
}

function choose(style: ShapeStyle) {
  if (style !== props.modelValue) emit('update:modelValue', style)
}

function onKeydown(event: KeyboardEvent, index: number) {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
  if (!step) return
  event.preventDefault()
  // Keep the editor's own arrow-key nudging out of this.
  event.stopPropagation()
  const list = styles.value
  const next = (index + step + list.length) % list.length
  choose(list[next]!)
  buttons.value[next]?.focus()
}
</script>

<template>
  <div
    class="grid grid-cols-4 gap-1.5"
    role="radiogroup"
    :aria-labelledby="labelledby"
    data-testid="style-picker"
  >
    <HintTooltip v-for="(style, i) in styles" :key="style" :label="t(shapeStyleLabelKey(style))">
      <button
        :ref="(el) => setButton(i, el)"
        type="button"
        role="radio"
        :aria-checked="style === modelValue"
        :tabindex="style === modelValue ? 0 : -1"
        :aria-label="t(shapeStyleLabelKey(style))"
        class="focus-visible:ring-ring/50 flex flex-col items-center gap-1 rounded-md border p-1 text-[11px] leading-tight outline-none focus-visible:ring-[3px]"
        :class="
          style === modelValue
            ? 'border-primary bg-primary/10 text-foreground font-medium'
            : 'hover:bg-accent text-foreground/80 border-transparent'
        "
        :data-testid="`style-${style}`"
        @click="choose(style)"
        @keydown="onKeydown($event, i)"
      >
        <svg viewBox="0 0 32 20" class="map-ground h-5 w-8 rounded-sm" aria-hidden="true">
          <g
            class="venue-shape"
            :class="shapeStyleClass(style)"
            :data-kind="kind === 'path' ? 'path' : 'rect'"
          >
            <polyline
              v-if="kind === 'path'"
              points="3,15 14,6 29,12"
              class="vs-body"
              fill="none"
              stroke-linecap="round"
              stroke-linejoin="round"
              style="stroke-width: 5px"
            />
            <text
              v-else-if="kind === 'label'"
              x="16"
              y="11"
              text-anchor="middle"
              dominant-baseline="central"
              font-size="12"
              font-weight="700"
              stroke-width="2"
              paint-order="stroke"
              class="venue-shape-label vs-label-kind"
              :class="shapeStyleClass(style)"
            >
              Aa
            </text>
            <rect v-else x="3" y="3" width="26" height="14" rx="2" class="vs-body" />
          </g>
        </svg>
        <span class="line-clamp-2 w-full break-words hyphens-auto">{{
          t(shapeStyleLabelKey(style))
        }}</span>
      </button>
    </HintTooltip>
  </div>
</template>
