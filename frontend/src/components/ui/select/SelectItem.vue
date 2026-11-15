<script setup lang="ts">
import {
  type HTMLAttributes,
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  onUpdated,
  ref,
} from 'vue'

import { Check } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { SelectItemProps } from 'reka-ui'
import {
  SelectItem,
  SelectItemIndicator,
  SelectItemText,
  injectSelectRootContext,
  useForwardProps,
} from 'reka-ui'

import { cn } from '@/lib/utils'

import { injectSelectPhoneContext } from './SelectContent.vue'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<SelectItemProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)

// ── Phone (not stock shadcn; see SelectContent.vue) ─────────────────────────
const phone = injectSelectPhoneContext(null)
const root = phone ? injectSelectRootContext() : null

const isSelected = computed(() => root?.modelValue.value === props.value)

// The hidden copy registers the option's text, as reka's own item does, so
// the trigger can show it. Only its own entry is ever removed: on a resize
// across the line reka's items and these come and go in the same tick.
type SelectOption = Parameters<NonNullable<typeof root>['onOptionAdd']>[0]
const text = ref<HTMLElement>()
let option: SelectOption | null = null

function register() {
  if (!root || !text.value) return
  if (option) root.optionsSet.value.delete(option)
  option = {
    value: props.value,
    disabled: !!props.disabled,
    textContent: text.value.textContent ?? '',
  }
  root.onOptionAdd(option)
}

onMounted(() => {
  if (phone?.mode === 'register') void nextTick(register)
})
onUpdated(() => {
  if (phone?.mode === 'register') register()
})
onUnmounted(() => {
  if (option) root?.optionsSet.value.delete(option)
})

/**
 * Only a press that started on this row picks it. The tap that opened the
 * dialog ends in a click the browser sends to whatever is under the finger by
 * then, which may well be a row. The keyboard clicks with `detail` 0.
 */
let pressed = false

function press() {
  pressed = true
}

function release() {
  pressed = false
}

function choose(event: MouseEvent) {
  const deliberate = pressed || event.detail === 0
  pressed = false
  if (!deliberate || props.disabled || !root) return
  root.onValueChange(props.value)
  root.onOpenChange(false)
}
</script>

<template>
  <span v-if="phone?.mode === 'register'" ref="text">
    <slot />
  </span>

  <button
    v-else-if="phone"
    type="button"
    role="option"
    data-slot="select-item"
    :aria-selected="isSelected"
    :data-state="isSelected ? 'checked' : 'unchecked'"
    :disabled="disabled"
    v-bind="$attrs"
    :class="
      cn(
        `hover:bg-accent active:bg-accent focus-visible:bg-accent focus-visible:ring-ring/50 [&_svg:not([class*='text-'])]:text-muted-foreground relative flex min-h-12 w-full cursor-pointer items-center gap-3 rounded-md px-4 py-2 text-left text-base outline-hidden select-none focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50 data-[state=checked]:font-medium [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4`,
        props.class,
      )
    "
    @pointerdown="press"
    @pointercancel="release"
    @click="choose"
  >
    <span class="flex min-w-0 flex-1 items-center gap-2">
      <slot />
    </span>
    <Check v-if="isSelected" class="text-primary size-5" aria-hidden="true" />
  </button>

  <SelectItem
    v-else
    data-slot="select-item"
    v-bind="{ ...forwardedProps, ...$attrs }"
    :class="
      cn(
        `focus:bg-accent focus:text-accent-foreground [&_svg:not([class*='text-'])]:text-muted-foreground relative flex w-full cursor-pointer items-center gap-2 rounded-sm py-1.5 pr-8 pl-2 text-sm outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 *:[span]:last:flex *:[span]:last:items-center *:[span]:last:gap-2`,
        props.class,
      )
    "
  >
    <span class="absolute right-2 flex size-3.5 items-center justify-center">
      <SelectItemIndicator>
        <Check class="size-4" />
      </SelectItemIndicator>
    </span>

    <SelectItemText>
      <slot />
    </SelectItemText>
  </SelectItem>
</template>
