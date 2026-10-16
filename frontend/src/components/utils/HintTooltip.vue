<script setup lang="ts">
/**
 * The app's hover/focus hint for a control. Use this instead of the HTML
 * `title` attribute: native titles look out of place, ignore the theme and
 * never show for keyboard focus.
 *
 *   <HintTooltip :label="t('notifications.dismiss')">
 *     <Button size="icon" :aria-label="t('notifications.dismiss')">…</Button>
 *   </HintTooltip>
 *
 * - The default slot is the trigger and is rendered `as-child`, so it must be a
 *   single element or a component that forwards attributes (shadcn `Button`
 *   does). A disabled `<button>` gets no pointer events: wrap it in a `<span>`.
 * - Tooltips never appear on touch, so an icon-only control still needs its
 *   own `aria-label`; the tooltip is not its accessible name.
 * - An empty `label` (or `disabled`) switches the tooltip off. The trigger
 *   stays mounted either way, so toggling `disabled` never replaces the child
 *   (which would drop keyboard focus).
 * - The trigger gets the tooltip's `data-state` (`closed`, `delayed-open`…),
 *   which overrides a child's own `data-state`: style a wrapped `Toggle` with
 *   `aria-pressed:` rather than `data-[state=on]:`.
 * - Around a menu trigger (`HintTooltip > DropdownMenuTrigger as-child >
 *   Button`), the menu trigger registers with the tooltip as its anchor, so the
 *   menu content must be told where it is: give it `:reference` (the button's
 *   element), or it opens off-screen. See `VenueEditorToolbar.vue`.
 * - It uses the nearest `TooltipProvider` (App.vue and the sidebar provide one)
 *   and brings its own when there is none, e.g. in the prerender or a unit test.
 */
import { type FunctionalComponent, computed, h, ref, watch } from 'vue'

import { injectTooltipProviderContext } from 'reka-ui'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const props = withDefaults(
  defineProps<{
    label?: string | null
    side?: 'top' | 'right' | 'bottom' | 'left'
    align?: 'start' | 'center' | 'end'
    disabled?: boolean
  }>(),
  { label: null, side: 'top', align: 'center', disabled: false },
)

// Same delay as the app-wide provider in App.vue.
const OwnProvider: FunctionalComponent = (_, { slots }) =>
  h(TooltipProvider, { delayDuration: 300 }, slots)
const PassThrough: FunctionalComponent = (_, { slots }) => slots.default?.()

const Wrapper = injectTooltipProviderContext(null) ? PassThrough : OwnProvider

const active = computed(() => !props.disabled && !!props.label)

// A control that turns disabled under the pointer or focus gets no `blur` or
// `pointerleave`, so close the hint here rather than leave it hanging.
const open = ref(false)
watch(active, (on) => {
  if (!on) open.value = false
})
</script>

<template>
  <component :is="Wrapper">
    <Tooltip v-model:open="open" :disabled="!active">
      <TooltipTrigger as-child>
        <slot />
      </TooltipTrigger>
      <TooltipContent v-if="active" :side="side" :align="align">
        {{ label }}
      </TooltipContent>
    </Tooltip>
  </component>
</template>
