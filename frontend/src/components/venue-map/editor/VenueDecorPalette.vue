<script setup lang="ts">
import { computed, ref } from 'vue'

import { useI18n } from 'vue-i18n'

import VenuePropGlyph from '@/components/venue-map/VenuePropGlyph.vue'

import {
  LINE_PRESETS,
  PROP_GROUPS,
  type PropGroup,
  type PropType,
  propLabelKey,
} from '@/lib/venue-decor'
import { shapeStyleClass } from '@/lib/venue-shapes'

/**
 * The decorations to put on a plan: trees, benches, tents, … each drawn with
 * the map's own glyph (`VenuePropGlyph`), so a button shows exactly what lands
 * on the map, in the current theme.
 *
 * - `stamp`: the floating strip over the canvas while the Deko tool is on.
 *   One scrollable row, grouped (Plants, Furniture, Event), then "Lines &
 *   areas" (hedge, fence, stream, path, sand), which switch to the line or
 *   shape tool with that look. Below it a note that decoration is no place.
 * - `picker`: the "Type" grid of the side panel for a selected decoration.
 *
 * The decorations form a radio group: the arrow keys move the choice (and are
 * kept from the editor, which would otherwise nudge the selection).
 */
const props = withDefaults(
  defineProps<{
    modelValue: PropType | null
    mode: 'stamp' | 'picker'
    disabled?: boolean
    labelledby?: string
  }>(),
  { disabled: false, labelledby: undefined },
)

const emit = defineEmits<{
  'update:modelValue': [prop: PropType]
  'pick-line': [key: LineKey]
  'pick-area': [style: 'sand']
}>()

type LineKey = keyof typeof LINE_PRESETS

const { t } = useI18n()

const GROUPS: readonly PropGroup[] = ['nature', 'furniture', 'event']
const LINES: readonly LineKey[] = ['hedge', 'fence', 'water', 'path']

/** Every decoration in palette order, for the arrow keys. */
const ordered = computed(() => GROUPS.flatMap((g) => PROP_GROUPS[g]))
const buttons = ref<Record<string, HTMLButtonElement | null>>({})

function setButton(prop: PropType, el: unknown) {
  buttons.value[prop] = (el as HTMLButtonElement | null) ?? null
}

/** The decoration that takes Tab focus: the chosen one, else the first. */
const focusable = computed(() => props.modelValue ?? ordered.value[0])

function choose(prop: PropType) {
  if (props.disabled) return
  emit('update:modelValue', prop)
}

function onKeydown(event: KeyboardEvent, prop: PropType) {
  const keys: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }
  let step = keys[event.key]
  if (event.key === 'Home' || event.key === 'End') step = 0
  if (step === undefined) return
  event.preventDefault()
  // Keep the editor's own arrow-key nudging out of this.
  event.stopPropagation()
  const list = ordered.value
  const index = list.indexOf(prop)
  const nextIndex =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? list.length - 1
        : (index + step + list.length) % list.length
  const next = list[nextIndex]!
  choose(next)
  buttons.value[next]?.focus()
}

const itemSize = computed(() =>
  props.mode === 'stamp' ? 'size-10 pointer-coarse:size-11' : 'aspect-square w-full',
)
</script>

<template>
  <div
    v-if="mode === 'stamp'"
    class="bg-background/95 flex flex-col gap-1 rounded-md border p-1.5 shadow-md"
    data-testid="decor-palette"
  >
    <div class="flex items-center gap-1.5 overflow-x-auto overscroll-x-contain pb-0.5">
      <div
        class="flex shrink-0 items-center gap-1.5"
        role="radiogroup"
        :aria-label="t('mapEditor.decor.title')"
      >
        <template v-for="(group, gi) in GROUPS" :key="group">
          <span v-if="gi > 0" class="bg-border mx-0.5 h-8 w-px shrink-0" aria-hidden="true" />
          <span class="sr-only">{{ t(`mapEditor.decor.groups.${group}`) }}</span>
          <button
            v-for="prop in PROP_GROUPS[group]"
            :key="prop"
            :ref="(el) => setButton(prop, el)"
            type="button"
            role="radio"
            :aria-checked="prop === modelValue"
            :tabindex="prop === focusable ? 0 : -1"
            :title="t(propLabelKey(prop))"
            :aria-label="t(propLabelKey(prop))"
            :disabled="disabled"
            class="focus-visible:ring-ring/50 flex shrink-0 items-center justify-center rounded-md border bg-[var(--map-canvas)] outline-none focus-visible:ring-[3px] disabled:opacity-50"
            :class="[
              itemSize,
              prop === modelValue
                ? 'ring-2 ring-[var(--map-select)]'
                : 'hover:border-foreground/40',
            ]"
            :data-testid="`decor-item-${prop}`"
            @click="choose(prop)"
            @keydown="onKeydown($event, prop)"
          >
            <svg viewBox="-26 -26 52 52" class="size-8" aria-hidden="true">
              <VenuePropGlyph :prop="prop" />
            </svg>
          </button>
        </template>
      </div>

      <span class="bg-border mx-0.5 h-8 w-px shrink-0" aria-hidden="true" />
      <div
        class="flex shrink-0 items-center gap-1"
        role="group"
        :aria-label="t('mapEditor.decor.groups.lines')"
      >
        <button
          v-for="line in LINES"
          :key="line"
          type="button"
          :disabled="disabled"
          class="hover:bg-accent focus-visible:ring-ring/50 flex h-10 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs outline-none focus-visible:ring-[3px] disabled:opacity-50 pointer-coarse:h-11"
          :data-testid="`decor-line-${line}`"
          @click="emit('pick-line', line)"
        >
          <svg viewBox="0 0 24 16" class="map-ground h-4 w-6 rounded-sm" aria-hidden="true">
            <g
              class="venue-shape"
              :class="shapeStyleClass(LINE_PRESETS[line].style)"
              data-kind="path"
            >
              <polyline
                points="2,12 10,5 22,9"
                class="vs-body"
                fill="none"
                stroke-linecap="round"
                stroke-linejoin="round"
                style="stroke-width: 3.5px"
              />
            </g>
          </svg>
          {{ t(`mapEditor.decor.lines.${line}`) }}
        </button>
        <button
          type="button"
          :disabled="disabled"
          class="hover:bg-accent focus-visible:ring-ring/50 flex h-10 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs outline-none focus-visible:ring-[3px] disabled:opacity-50 pointer-coarse:h-11"
          data-testid="decor-area-sand"
          @click="emit('pick-area', 'sand')"
        >
          <svg viewBox="0 0 24 16" class="map-ground h-4 w-6 rounded-sm" aria-hidden="true">
            <g class="venue-shape" :class="shapeStyleClass('sand')" data-kind="polygon">
              <polygon points="3,4 20,2 22,13 6,14" class="vs-body" />
            </g>
          </svg>
          {{ t('mapEditor.decor.areas.sand') }}
        </button>
      </div>
    </div>
    <p class="text-muted-foreground px-0.5 text-xs" data-testid="decor-note">
      {{ t('mapEditor.decor.note') }}
    </p>
  </div>

  <div
    v-else
    class="grid grid-cols-5 gap-1.5"
    role="radiogroup"
    :aria-labelledby="labelledby"
    data-testid="decor-picker"
  >
    <button
      v-for="prop in ordered"
      :key="prop"
      :ref="(el) => setButton(prop, el)"
      type="button"
      role="radio"
      :aria-checked="prop === modelValue"
      :tabindex="prop === focusable ? 0 : -1"
      :title="t(propLabelKey(prop))"
      :aria-label="t(propLabelKey(prop))"
      :disabled="disabled"
      class="focus-visible:ring-ring/50 flex items-center justify-center rounded-md border bg-[var(--map-canvas)] p-0.5 outline-none focus-visible:ring-[3px] disabled:opacity-50"
      :class="[
        itemSize,
        prop === modelValue ? 'ring-2 ring-[var(--map-select)]' : 'hover:border-foreground/40',
      ]"
      :data-testid="`decor-type-${prop}`"
      @click="prop !== modelValue && choose(prop)"
      @keydown="onKeydown($event, prop)"
    >
      <svg viewBox="-26 -26 52 52" class="size-full" aria-hidden="true">
        <VenuePropGlyph :prop="prop" />
      </svg>
    </button>
  </div>
</template>
