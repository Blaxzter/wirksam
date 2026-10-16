<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { BringToFront, Copy, RotateCcw, RotateCw, SendToBack, Trash2, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

import HintTooltip from '@/components/utils/HintTooltip.vue'
import VenueDecorPalette from '@/components/venue-map/editor/VenueDecorPalette.vue'
import VenueStylePicker from '@/components/venue-map/editor/VenueStylePicker.vue'

import type { LocationRead, VenueShapeRead, VenueShapeUpdate } from '@/client/types.gen'
import {
  DEFAULT_PROP_SCALE,
  PROP_SCALE_RANGE,
  type PropType,
  ROTATION_STEP,
  isPropType,
  normaliseRotation,
  propLabelKey,
} from '@/lib/venue-decor'
import {
  LINKABLE_KINDS,
  MAX_LABEL_LENGTH,
  type ShapeStyle,
  shapeKindLabelKey,
} from '@/lib/venue-shapes'

/**
 * The side panel for the selected drawing: its look, caption, caption size
 * and position, line width (lines), linked place (rectangles and shapes),
 * order, duplicate and delete. A decoration (prop) gets its type, turn and
 * size instead of look and place: it is never a place. Also asks for the
 * words of a text that was just placed (`labelDraft`).
 *
 * It only reports what should change (`update` with a patch); the editor
 * turns that into one undoable step. Text fields report on change, Enter or
 * blur — not per keystroke.
 */
const props = defineProps<{
  shape: VenueShapeRead | null
  /** A text was placed on the map and waits for its words. */
  labelDraft?: boolean
  locations: LocationRead[]
  selectedVertex?: number | null
  /** The plan size in plan units (for the line width preview). */
  width: number
  height: number
}>()

const emit = defineEmits<{
  update: [patch: VenueShapeUpdate]
  duplicate: []
  delete: []
  reorder: [direction: 1 | -1]
  'remove-vertex': []
  'commit-label': [text: string]
  'cancel-label': []
  close: []
}>()

const { t } = useI18n()

const labelInput = ref<InstanceType<typeof Input> | null>(null)
const labelText = ref('')
const strokeWidth = ref(0.02)

const linkable = computed(
  () => !!props.shape && (LINKABLE_KINDS as readonly string[]).includes(props.shape.kind),
)
const isProp = computed(() => props.shape?.kind === 'prop')
const propType = computed<PropType | null>(() =>
  isPropType(props.shape?.prop) ? props.shape.prop : null,
)
/** Slider values while dragging; committed on `change`. */
const rotation = ref(0)
const scale = ref(DEFAULT_PROP_SCALE)
watch(
  () => [props.shape?.rotation, props.shape?.scale] as const,
  ([r, k]) => {
    rotation.value = r ?? 0
    scale.value = k ?? DEFAULT_PROP_SCALE
  },
  { immediate: true },
)

const heading = computed(() => {
  const s = props.shape
  if (!s) return ''
  if (s.kind === 'prop') {
    const name = s.label?.trim() || t(propLabelKey(s.prop ?? ''))
    return `${t('mapEditor.inspector.prop.title')} · ${name}`
  }
  return s.label?.trim() || t(shapeKindLabelKey(s.kind))
})

function turnBy(delta: number) {
  emit('update', { rotation: normaliseRotation((props.shape?.rotation ?? 0) + delta) })
}

function onRotationCommit() {
  const value = normaliseRotation(rotation.value)
  if (value !== (props.shape?.rotation ?? 0)) emit('update', { rotation: value })
}

function onScaleCommit() {
  const value = Math.round(scale.value * 1000) / 1000
  if (value !== (props.shape?.scale ?? DEFAULT_PROP_SCALE)) emit('update', { scale: value })
}

function onPropType(prop: PropType) {
  if (prop !== props.shape?.prop) emit('update', { prop })
}
const LABEL_SIZES = ['sm', 'md', 'lg'] as const

watch(
  () => [props.shape?.id, props.shape?.label, props.labelDraft] as const,
  () => {
    labelText.value = props.labelDraft ? '' : (props.shape?.label ?? '')
  },
  { immediate: true },
)
watch(
  () => props.shape?.stroke_width,
  (w) => {
    strokeWidth.value = w ?? 0.02
  },
  { immediate: true },
)

function focusLabel() {
  void nextTick(() => {
    const el = (labelInput.value?.$el ?? null) as HTMLInputElement | null
    el?.focus()
  })
}

defineExpose({ focusLabel })

let committed = false

function commitLabel() {
  if (props.labelDraft) {
    if (committed) return
    committed = true
    emit('commit-label', labelText.value)
    void nextTick(() => (committed = false))
    return
  }
  const shape = props.shape
  if (!shape) return
  const text = labelText.value.trim()
  if (shape.kind === 'label' && !text) {
    labelText.value = shape.label ?? ''
    return
  }
  if (text === (shape.label ?? '')) return
  emit('update', { label: text || null })
}

function onStyle(style: ShapeStyle) {
  emit('update', { style })
}

function onLink(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('update', { location_id: value || null })
}

function onStrokeCommit() {
  const value = Math.round(strokeWidth.value * 1000) / 1000
  if (value !== props.shape?.stroke_width) emit('update', { stroke_width: value })
}

/** The line width as it is drawn at the plan's full size, for the preview. */
const strokePreview = computed(() => {
  const units = strokeWidth.value * Math.min(props.width, props.height)
  // The preview box is 120 px for the plan's shorter side / 10.
  return Math.max(1, Math.min(18, (units / Math.min(props.width, props.height)) * 220))
})

const canRemoveVertex = computed(() => {
  const s = props.shape
  if (!s || props.selectedVertex == null) return false
  if (s.kind === 'polygon') return s.points.length > 3
  if (s.kind === 'path') return s.points.length > 2
  return false
})
</script>

<template>
  <section
    v-if="labelDraft"
    class="space-y-3 rounded-lg border p-3"
    :aria-label="t('mapEditor.inspector.newLabel')"
    data-testid="label-draft-panel"
  >
    <div class="space-y-1.5">
      <Label for="map-editor-label-draft">{{ t('mapEditor.inspector.newLabel') }}</Label>
      <Input
        id="map-editor-label-draft"
        ref="labelInput"
        v-model="labelText"
        :maxlength="MAX_LABEL_LENGTH"
        :placeholder="t('mapEditor.draw.labelPlaceholder')"
        data-testid="label-draft-input"
        @keydown.enter.prevent="commitLabel"
        @keydown.escape.prevent="emit('cancel-label')"
        @blur="commitLabel"
      />
    </div>
    <div class="flex gap-2">
      <Button size="sm" class="flex-1" data-testid="label-draft-save" @click="commitLabel">
        {{ t('common.actions.save') }}
      </Button>
      <Button size="sm" variant="ghost" @click="emit('cancel-label')">
        {{ t('mapEditor.draw.cancel') }}
      </Button>
    </div>
  </section>

  <section
    v-else-if="shape"
    class="space-y-4 rounded-lg border p-3"
    :aria-label="t('mapEditor.inspector.title')"
    data-testid="shape-inspector"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <p class="text-muted-foreground text-xs">{{ t('mapEditor.inspector.title') }}</p>
        <p class="truncate font-medium" data-testid="shape-inspector-heading">
          {{ heading }}
        </p>
      </div>
      <HintTooltip :label="t('mapEditor.marker.close')">
        <Button
          size="icon-sm"
          variant="ghost"
          :aria-label="t('mapEditor.marker.close')"
          data-testid="shape-inspector-close"
          @click="emit('close')"
        >
          <X />
        </Button>
      </HintTooltip>
    </div>

    <template v-if="isProp">
      <div class="space-y-1.5">
        <p id="map-editor-prop-type" class="text-sm font-medium">
          {{ t('mapEditor.inspector.prop.type') }}
        </p>
        <VenueDecorPalette
          :model-value="propType"
          mode="picker"
          labelledby="map-editor-prop-type"
          @update:model-value="onPropType"
        />
      </div>

      <div class="space-y-1.5">
        <div class="flex items-center justify-between gap-2">
          <Label for="map-editor-prop-rotation">{{ t('mapEditor.inspector.prop.rotation') }}</Label>
          <span class="text-muted-foreground text-xs tabular-nums" data-testid="prop-rotation-value"
            >{{ Math.round(rotation) }}°</span
          >
        </div>
        <div class="flex items-center gap-2">
          <HintTooltip :label="`${t('mapEditor.inspector.prop.rotateLeft')} (Q)`">
            <Button
              size="icon-sm"
              variant="outline"
              :aria-label="t('mapEditor.inspector.prop.rotateLeft')"
              aria-keyshortcuts="Q"
              data-testid="prop-rotate-left"
              @click="turnBy(-ROTATION_STEP)"
            >
              <RotateCcw />
            </Button>
          </HintTooltip>
          <input
            id="map-editor-prop-rotation"
            v-model.number="rotation"
            type="range"
            min="0"
            max="359"
            step="1"
            class="accent-primary min-w-0 flex-1"
            data-testid="prop-rotation"
            @change="onRotationCommit"
          />
          <HintTooltip :label="`${t('mapEditor.inspector.prop.rotateRight')} (E)`">
            <Button
              size="icon-sm"
              variant="outline"
              :aria-label="t('mapEditor.inspector.prop.rotateRight')"
              aria-keyshortcuts="E"
              data-testid="prop-rotate-right"
              @click="turnBy(ROTATION_STEP)"
            >
              <RotateCw />
            </Button>
          </HintTooltip>
        </div>
      </div>

      <div class="space-y-1.5">
        <div class="flex items-center justify-between gap-2">
          <Label for="map-editor-prop-scale">{{ t('mapEditor.inspector.prop.size') }}</Label>
          <span class="text-muted-foreground text-xs tabular-nums" data-testid="prop-scale-value"
            >{{ Math.round(scale * 100) }} %</span
          >
        </div>
        <div class="flex items-center gap-2">
          <input
            id="map-editor-prop-scale"
            v-model.number="scale"
            type="range"
            :min="PROP_SCALE_RANGE[0]"
            :max="PROP_SCALE_RANGE[1]"
            step="0.05"
            class="accent-primary min-w-0 flex-1"
            data-testid="prop-scale"
            @change="onScaleCommit"
          />
          <Button
            size="xs"
            variant="ghost"
            :disabled="(shape.scale ?? DEFAULT_PROP_SCALE) === DEFAULT_PROP_SCALE"
            data-testid="prop-scale-reset"
            @click="emit('update', { scale: DEFAULT_PROP_SCALE })"
          >
            {{ t('mapEditor.inspector.prop.resetSize') }}
          </Button>
        </div>
        <p class="text-muted-foreground text-xs">{{ t('mapEditor.inspector.prop.keysHint') }}</p>
      </div>
    </template>

    <div v-else class="space-y-1.5">
      <p id="map-editor-shape-style" class="text-sm font-medium">
        {{ t('mapEditor.inspector.style') }}
      </p>
      <VenueStylePicker
        :model-value="shape.style"
        :kind="shape.kind"
        labelledby="map-editor-shape-style"
        @update:model-value="onStyle"
      />
    </div>

    <div class="space-y-1.5">
      <Label for="map-editor-shape-label">{{ t('mapEditor.inspector.label') }}</Label>
      <Input
        id="map-editor-shape-label"
        ref="labelInput"
        v-model="labelText"
        :maxlength="MAX_LABEL_LENGTH"
        :placeholder="t('mapEditor.draw.labelPlaceholder')"
        data-testid="shape-label"
        @change="commitLabel"
        @keydown.enter.prevent="commitLabel"
        @blur="commitLabel"
      />
    </div>

    <div v-if="shape.label?.trim()" class="space-y-1.5">
      <p id="map-editor-label-size" class="text-sm font-medium">
        {{ t('mapEditor.inspector.labelSize') }}
      </p>
      <div class="flex gap-1" role="group" aria-labelledby="map-editor-label-size">
        <Button
          v-for="size in LABEL_SIZES"
          :key="size"
          size="xs"
          :variant="shape.label_size === size ? 'default' : 'outline'"
          :aria-pressed="shape.label_size === size"
          :data-testid="`label-size-${size}`"
          @click="shape.label_size !== size && emit('update', { label_size: size })"
        >
          {{ t(`mapEditor.inspector.labelSizes.${size}`) }}
        </Button>
      </div>
      <template v-if="shape.kind !== 'label' && shape.kind !== 'prop'">
        <p class="text-muted-foreground text-xs">{{ t('mapEditor.inspector.moveLabelHint') }}</p>
        <Button
          v-if="shape.label_x != null"
          size="xs"
          variant="ghost"
          data-testid="label-reset"
          @click="emit('update', { label_x: null, label_y: null })"
        >
          {{ t('mapEditor.inspector.resetLabel') }}
        </Button>
      </template>
    </div>

    <div v-if="shape.kind === 'path'" class="space-y-1.5">
      <Label for="map-editor-stroke">{{ t('mapEditor.inspector.strokeWidth') }}</Label>
      <div class="flex items-center gap-3">
        <input
          id="map-editor-stroke"
          v-model.number="strokeWidth"
          type="range"
          min="0.005"
          max="0.08"
          step="0.001"
          class="accent-primary min-w-0 flex-1"
          data-testid="shape-stroke"
          @change="onStrokeCommit"
        />
        <svg viewBox="0 0 40 20" class="h-5 w-10 shrink-0" aria-hidden="true">
          <line
            x1="4"
            y1="10"
            x2="36"
            y2="10"
            class="stroke-foreground/70"
            stroke-linecap="round"
            :stroke-width="strokePreview"
          />
        </svg>
      </div>
    </div>

    <div v-if="linkable" class="space-y-1.5">
      <Label for="map-editor-shape-link">{{ t('mapEditor.inspector.link') }}</Label>
      <NativeSelect
        id="map-editor-shape-link"
        :model-value="shape.location_id ?? ''"
        class="w-full"
        data-testid="shape-link"
        @change="onLink"
      >
        <NativeSelectOption value="">{{ t('mapEditor.inspector.linkNone') }}</NativeSelectOption>
        <NativeSelectOption v-for="loc in locations" :key="loc.id" :value="loc.id">
          {{ loc.name }}
        </NativeSelectOption>
      </NativeSelect>
      <p class="text-muted-foreground text-xs">{{ t('mapEditor.inspector.linkHint') }}</p>
    </div>

    <Button
      v-if="canRemoveVertex"
      size="sm"
      variant="outline"
      class="w-full"
      data-testid="shape-remove-vertex"
      @click="emit('remove-vertex')"
    >
      {{ t('mapEditor.inspector.removePoint') }}
    </Button>

    <div class="space-y-1.5">
      <p class="text-sm font-medium">{{ t('mapEditor.inspector.order') }}</p>
      <div class="grid grid-cols-2 gap-2">
        <Button
          size="sm"
          variant="outline"
          aria-keyshortcuts="["
          data-testid="shape-back"
          @click="emit('reorder', -1)"
        >
          <SendToBack />
          {{ t('mapEditor.inspector.back') }}
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-keyshortcuts="]"
          data-testid="shape-forward"
          @click="emit('reorder', 1)"
        >
          <BringToFront />
          {{ t('mapEditor.inspector.forward') }}
        </Button>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2">
      <Button size="sm" variant="outline" data-testid="shape-duplicate" @click="emit('duplicate')">
        <Copy />
        {{ t('mapEditor.inspector.duplicate') }}
      </Button>
      <Button
        size="sm"
        variant="outline"
        class="text-destructive"
        aria-keyshortcuts="Delete"
        data-testid="shape-delete"
        @click="emit('delete')"
      >
        <Trash2 />
        {{ t('mapEditor.inspector.delete') }}
      </Button>
    </div>
  </section>
</template>
