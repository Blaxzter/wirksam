<script setup lang="ts">
/**
 * The hover/focus hint for the pins on a venue plan: the app's tooltip in
 * place of the SVG `<title>` the pins used to carry.
 *
 * A pin is an SVG `<g>`, and a tooltip's content cannot be rendered from inside
 * an `<svg>` (Vue would create the teleported box as SVG elements), so the pins
 * cannot be wrapped in `HintTooltip`. Instead this component sits next to the
 * `<svg>`, listens on it for any element carrying `data-hint` (both
 * `VenueMarkerPill` and `VenueMarkerGlyph` set it) and points one shared
 * tooltip at that element.
 *
 * It follows `HintTooltip`'s rules: a short delay on hover, at once on keyboard
 * focus, never on touch, and gone as soon as the pointer goes down (a click,
 * a drag or a pan) or the wheel zooms the plan.
 */
import { type FunctionalComponent, computed, h, onBeforeUnmount, ref } from 'vue'

import { useEventListener } from '@vueuse/core'
import { injectTooltipProviderContext } from 'reka-ui'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const props = defineProps<{
  /** The element holding the pins, normally the plan's `<svg>`. */
  container: Element | null | undefined
}>()

/** Same delay as the app-wide provider in App.vue. */
const DELAY_MS = 300

const OwnProvider: FunctionalComponent = (_, { slots }) =>
  h(TooltipProvider, { delayDuration: DELAY_MS }, slots)
const PassThrough: FunctionalComponent = (_, { slots }) => slots.default?.()
const Wrapper = injectTooltipProviderContext(null) ? PassThrough : OwnProvider

const target = ref<Element | null>(null)
const label = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let pending: Element | null = null

function pinOf(node: EventTarget | null): Element | null {
  const el = node instanceof Element ? node.closest('[data-hint]') : null
  return el && props.container?.contains(el) ? el : null
}

function show(pin: Element) {
  const text = pin.getAttribute('data-hint')
  if (!text) return
  label.value = text
  target.value = pin
}

function hide() {
  clearTimeout(timer)
  pending = null
  target.value = null
}

function onPointerOver(event: PointerEvent) {
  // Never on touch, and not while a button is held (a drag or a pan).
  if (event.pointerType === 'touch' || event.buttons !== 0) return
  const pin = pinOf(event.target)
  if (!pin) {
    hide()
    return
  }
  if (pin === target.value || pin === pending) return
  clearTimeout(timer)
  // Moving from one pin straight to the next: no second wait.
  if (target.value) {
    show(pin)
    return
  }
  pending = pin
  timer = setTimeout(() => {
    pending = null
    show(pin)
  }, DELAY_MS)
}

function onPointerOut(event: PointerEvent) {
  const from = pinOf(event.target)
  if (from && from !== pinOf(event.relatedTarget)) hide()
}

function onFocusIn(event: FocusEvent) {
  const pin = pinOf(event.target)
  // Only keyboard focus: a click focuses the pin too, and then it is selected.
  if (pin && pin.matches(':focus-visible')) show(pin)
}

const container = computed(() => props.container ?? null)
useEventListener(container, 'pointerover', onPointerOver)
useEventListener(container, 'pointerout', onPointerOut)
useEventListener(container, 'pointerdown', hide)
useEventListener(container, 'wheel', hide, { passive: true })
useEventListener(container, 'focusin', onFocusIn)
useEventListener(container, 'focusout', hide)
onBeforeUnmount(() => clearTimeout(timer))

defineExpose({ hide })
</script>

<template>
  <component :is="Wrapper">
    <Tooltip :open="!!target" :delay-duration="0" @update:open="(open: boolean) => !open && hide()">
      <TooltipTrigger as-child :reference="target ?? undefined">
        <span aria-hidden="true" class="pointer-events-none absolute size-0" />
      </TooltipTrigger>
      <TooltipContent v-if="target" side="top" data-testid="map-pin-hint">
        {{ label }}
      </TooltipContent>
    </Tooltip>
  </component>
</template>
