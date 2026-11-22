<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, Undo2 } from '@lucide/vue'
import { RadioGroupItem, RadioGroupRoot } from 'reka-ui'
import { useI18n } from 'vue-i18n'

import { Input } from '@/components/ui/input'

import { hexToOklch, isHexColour } from '@/lib/colour-math'
import { type ColourKind, type ModeReport, customColour } from '@/lib/custom-colour'
import {
  EVENT_BASE_COLORS,
  EVENT_PRIMARY_COLORS,
  EVENT_SECONDARY_COLORS,
  eventColourAttr,
} from '@/lib/event-appearance'

/**
 * One of an event's colours: the default, a preset, or an own colour. Used by
 * the organisers' "Colour and logo" card, which saves each pick, and by the
 * example view on the feature page, which only shows it.
 *
 * An own colour is picked with the browser's colour field or typed as a code.
 * The organisers then see what it became in light and dark mode, and how well
 * text reads on it: `custom-colour.ts` moves its lightness as far as WCAG AA
 * needs and no further. A pick is handed on when it is done (the colour field
 * closed, the code confirmed), not while the colour field is being dragged.
 */
const props = defineProps<{
  kind: ColourKind
  modelValue: string | null | undefined
  /** The main colour, for the base tone that follows it. */
  primary?: string | null
  disabled?: boolean
  /** Keeps ids apart where a page has two pickers of a kind. */
  idPrefix?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const { t, locale } = useI18n()

/** The radio values that are not a colour: reka wants strings. */
const NONE = 'none'
const OWN = 'own'
/** Where an own colour starts before one is picked: a club blue. */
const FIRST_OWN = '#1e6bb8'

const PRESETS: Record<ColourKind, readonly string[]> = {
  primary: EVENT_PRIMARY_COLORS,
  secondary: EVENT_SECONDARY_COLORS,
  base: EVENT_BASE_COLORS,
}

const id = computed(() => `${props.idPrefix ?? 'event'}-colour-${props.kind}`)

const isOwn = (value: unknown): value is string => isHexColour(value)
const ownOpen = ref(isOwn(props.modelValue))
const draft = ref(isOwn(props.modelValue) ? props.modelValue.toLowerCase() : FIRST_OWN)
const code = ref(draft.value)
const invalid = ref(false)

watch(
  () => props.modelValue,
  (value) => {
    if (isOwn(value)) {
      ownOpen.value = true
      draft.value = value.toLowerCase()
      code.value = draft.value
    } else {
      ownOpen.value = false
    }
  },
)

const selected = computed(() => (ownOpen.value ? OWN : (props.modelValue ?? NONE)))

function onPick(value: string) {
  if (value === OWN) {
    // Opens the colour field; nothing changes until a colour is picked.
    ownOpen.value = true
    return
  }
  ownOpen.value = false
  emit('update:modelValue', value === NONE ? null : value)
}

function preview(value: string) {
  draft.value = value.toLowerCase()
  code.value = draft.value
  invalid.value = false
}

function commit(value: string) {
  preview(value)
  if (draft.value !== props.modelValue?.toLowerCase()) emit('update:modelValue', draft.value)
}

function commitCode() {
  const typed = code.value.trim()
  const value = typed.startsWith('#') ? typed : `#${typed}`
  if (!isOwn(value)) {
    invalid.value = true
    return
  }
  commit(value)
}

const label = (name: string) =>
  props.kind === 'base' && name === 'primary'
    ? t('duties.events.appearance.colour.base.followPrimary')
    : t(`duties.events.appearance.colour.names.${name}`)

const presets = computed(() =>
  PRESETS[props.kind].map((name) => ({ value: name, label: label(name) })),
)

/** `data-event-*` for a swatch: its own preset, the draft for "own". */
const ownAttr = computed(() => eventColourAttr(props.kind, draft.value))
const primaryAttr = computed(() => eventColourAttr('primary', props.primary))

const report = computed(() => customColour(props.kind, draft.value).report)

const ratio = (value: number) =>
  value.toLocaleString(locale.value, { minimumFractionDigits: 1, maximumFractionDigits: 1 })

function describe(mode: ModeReport) {
  const key = 'duties.events.appearance.colour.custom'
  if (!mode.adjusted) return t(`${key}.asPicked`, { ratio: ratio(mode.ratio) })
  const darker = hexToOklch(mode.used).l < hexToOklch(draft.value).l
  return t(`${key}.${darker ? 'darkened' : 'lightened'}`, {
    ratio: ratio(mode.ratio),
    before: ratio(mode.originalRatio),
  })
}

const SWATCH =
  'flex size-9 items-center justify-center rounded-full ring-offset-2 ring-offset-card group-data-[state=checked]:ring-2'
/** The "own" swatch before a colour is picked: every colour at once. */
const RAINBOW =
  'conic-gradient(oklch(0.65 0.2 25), oklch(0.8 0.17 90), oklch(0.7 0.17 150), oklch(0.65 0.13 220), oklch(0.6 0.2 300), oklch(0.65 0.2 25))'
</script>

<template>
  <section class="space-y-3" :data-testid="`event-colour-${kind}`">
    <div>
      <h3 :id="`${id}-label`" class="text-sm font-medium">
        {{ t(`duties.events.appearance.colour.${kind}.title`) }}
      </h3>
      <p class="text-xs text-muted-foreground">
        {{ t(`duties.events.appearance.colour.${kind}.hint`) }}
      </p>
    </div>
    <RadioGroupRoot
      :model-value="selected"
      :disabled="disabled"
      :aria-labelledby="`${id}-label`"
      class="grid grid-cols-5 gap-2 sm:grid-cols-11"
      @update:model-value="(v) => onPick(String(v))"
    >
      <RadioGroupItem
        :value="NONE"
        :data-testid="`event-${kind}-none`"
        class="group flex flex-col items-center gap-1.5 rounded-lg p-1.5 text-center text-xs outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait"
      >
        <span
          class="flex size-9 items-center justify-center rounded-full border-2 border-dashed border-muted-foreground/50 text-muted-foreground"
        >
          <Check v-if="selected === NONE" class="size-4" />
          <Undo2 v-else class="size-4" />
        </span>
        <span
          class="text-muted-foreground group-data-[state=checked]:font-medium group-data-[state=checked]:text-foreground"
        >
          {{ t('duties.events.appearance.colour.none') }}
        </span>
      </RadioGroupItem>

      <RadioGroupItem
        v-for="option in presets"
        :key="option.value"
        :value="option.value"
        :data-testid="`event-${kind}-${option.value}`"
        class="group flex flex-col items-center gap-1.5 rounded-lg p-1.5 text-center text-xs outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait"
      >
        <span
          v-if="kind === 'primary'"
          :data-event-primary="option.value"
          :class="SWATCH"
          class="bg-(--event-primary) text-(--event-primary-foreground) group-data-[state=checked]:ring-(--event-primary)"
        >
          <Check v-if="selected === option.value" class="size-4" />
        </span>
        <span
          v-else-if="kind === 'secondary'"
          :data-event-secondary="option.value"
          :class="SWATCH"
          class="bg-(--event-secondary) text-(--event-secondary-foreground) group-data-[state=checked]:ring-foreground"
        >
          <Check v-if="selected === option.value" class="size-4" />
        </span>
        <!-- A base tone that follows the main colour shows the one chosen. -->
        <span
          v-else
          :data-event-base="option.value"
          :data-event-primary="option.value === 'primary' ? primaryAttr : undefined"
          :class="SWATCH"
          class="event-base-swatch border text-foreground group-data-[state=checked]:ring-foreground"
        >
          <Check v-if="selected === option.value" class="size-4" />
        </span>
        <span
          class="text-muted-foreground group-data-[state=checked]:font-medium group-data-[state=checked]:text-foreground"
        >
          {{ option.label }}
        </span>
      </RadioGroupItem>

      <RadioGroupItem
        :value="OWN"
        :data-testid="`event-${kind}-own`"
        class="group flex flex-col items-center gap-1.5 rounded-lg p-1.5 text-center text-xs outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait"
      >
        <span
          v-if="ownOpen && kind === 'primary'"
          :data-event-primary="ownAttr"
          :class="SWATCH"
          class="bg-(--event-primary) text-(--event-primary-foreground) group-data-[state=checked]:ring-(--event-primary)"
        >
          <Check class="size-4" />
        </span>
        <span
          v-else-if="ownOpen && kind === 'secondary'"
          :data-event-secondary="ownAttr"
          :class="SWATCH"
          class="bg-(--event-secondary) text-(--event-secondary-foreground) group-data-[state=checked]:ring-foreground"
        >
          <Check class="size-4" />
        </span>
        <span
          v-else-if="ownOpen"
          :data-event-base="ownAttr"
          :class="SWATCH"
          class="event-base-swatch border text-foreground group-data-[state=checked]:ring-foreground"
        >
          <Check class="size-4" />
        </span>
        <span v-else :class="SWATCH" :style="{ background: RAINBOW }" />
        <span
          class="text-muted-foreground group-data-[state=checked]:font-medium group-data-[state=checked]:text-foreground"
        >
          {{ t('duties.events.appearance.colour.custom.own') }}
        </span>
      </RadioGroupItem>
    </RadioGroupRoot>

    <div
      v-if="ownOpen"
      class="space-y-3 rounded-lg border p-3"
      :data-testid="`event-${kind}-own-panel`"
    >
      <div class="flex flex-wrap items-end gap-3">
        <label class="space-y-1 text-xs font-medium">
          <span class="block">{{ t('duties.events.appearance.colour.custom.pick') }}</span>
          <input
            type="color"
            :value="draft"
            :disabled="disabled"
            class="block h-9 w-14 cursor-pointer rounded-md border bg-transparent p-0.5"
            :data-testid="`event-${kind}-own-input`"
            @input="preview(($event.target as HTMLInputElement).value)"
            @change="commit(($event.target as HTMLInputElement).value)"
          />
        </label>
        <label class="space-y-1 text-xs font-medium">
          <span class="block">{{ t('duties.events.appearance.colour.custom.code') }}</span>
          <Input
            v-model="code"
            :disabled="disabled"
            maxlength="7"
            spellcheck="false"
            class="h-9 w-28 font-mono"
            :aria-invalid="invalid || undefined"
            :data-testid="`event-${kind}-own-code`"
            @keydown.enter.prevent="commitCode"
            @blur="commitCode"
          />
        </label>
      </div>
      <p v-if="invalid" class="text-xs text-destructive" role="alert">
        {{ t('duties.events.appearance.colour.custom.invalid') }}
      </p>
      <ul v-if="report" class="space-y-1.5 text-xs" :data-testid="`event-${kind}-own-report`">
        <li
          v-for="mode in ['light', 'dark'] as const"
          :key="mode"
          class="flex items-start gap-2"
          :data-testid="`event-${kind}-own-${mode}`"
          :data-adjusted="report[mode].adjusted"
        >
          <span
            class="mt-px size-4 shrink-0 rounded-full border"
            :style="{ background: report[mode].used }"
            aria-hidden="true"
          />
          <span>
            <span class="font-medium"
              >{{ t(`duties.events.appearance.colour.custom.${mode}`) }}:</span
            >
            {{ describe(report[mode]) }}
          </span>
        </li>
      </ul>
      <p v-else class="text-xs text-muted-foreground">
        {{ t('duties.events.appearance.colour.custom.baseHint') }}
      </p>
    </div>
  </section>
</template>
