<script lang="ts">
import { type PropType, defineComponent } from 'vue'

import { createContext } from 'reka-ui'

/**
 * Not stock shadcn: on a phone the list opens as a dialog instead of a popup.
 *
 * reka's Select has no such mode — its list always floats beside the trigger —
 * so `SelectContent` and `SelectItem` render the phone version themselves on
 * top of reka's root state (`injectSelectRootContext`). Every option is
 * rendered twice there, and this says which copy a `SelectItem` is in:
 *
 * - `register` — a hidden copy that stays mounted, so the trigger can show the
 *   chosen option's text while the dialog is shut (reka's `SelectValue` reads
 *   it from the options its items register).
 * - `list` — the rows in the open dialog.
 */
export type SelectPhoneMode = 'register' | 'list'

export const [injectSelectPhoneContext, provideSelectPhoneContext] = createContext<{
  mode: SelectPhoneMode
}>('SelectPhone')

/** Renders its slot with `mode` for the `SelectItem`s inside it. */
const PhoneScope = defineComponent({
  props: { mode: { type: String as PropType<SelectPhoneMode>, required: true } },
  setup(props, { slots }) {
    provideSelectPhoneContext({ mode: props.mode })
    return () => slots.default?.()
  },
})
</script>

<script setup lang="ts">
import { type HTMLAttributes, ref, watch } from 'vue'

import { reactiveOmit, useMediaQuery } from '@vueuse/core'
import type { SelectContentEmits, SelectContentProps } from 'reka-ui'
import {
  SelectContent,
  SelectPortal,
  SelectViewport,
  injectSelectRootContext,
  useForwardPropsEmits,
} from 'reka-ui'
import { useI18n } from 'vue-i18n'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RESPONSIVE_DIALOG_MOBILE_QUERY } from '@/components/ui/responsive-dialog'

import { cn } from '@/lib/utils'

import { SelectScrollDownButton, SelectScrollUpButton } from '.'

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(
  defineProps<SelectContentProps & { class?: HTMLAttributes['class'] }>(),
  {
    position: 'popper',
  },
)
const emits = defineEmits<SelectContentEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)

// ── Phone: a dialog with a margin all round ─────────────────────────────────
// Not a bottom sheet: scrolling a long list down in a sheet kept pulling the
// sheet shut. The same line as `ResponsiveDialog`, so a dialog on a phone and
// the select inside it switch together.
const { t } = useI18n()
const isPhone = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)
const root = injectSelectRootContext()
const listbox = ref<HTMLElement>()

/**
 * The dialog's heading: what the trigger is labelled with, since the dialog
 * covers the trigger and its label. Read once on opening and kept while the
 * dialog fades out.
 */
const title = ref('')
watch(
  () => root.open.value,
  (open) => {
    if (open && isPhone.value) title.value = triggerLabel()
  },
)

function triggerLabel(): string {
  const trigger = root.triggerElement.value
  const fromLabel = (trigger as HTMLButtonElement | undefined)?.labels?.[0]?.textContent
  const fromLabelledBy = trigger
    ?.getAttribute('aria-labelledby')
    ?.split(/\s+/)
    .map((id) => document.getElementById(id)?.textContent ?? '')
    .join(' ')
  const label = fromLabel || fromLabelledBy || trigger?.getAttribute('aria-label') || ''
  return label.trim() || t('common.select.choose')
}

/** Open on the chosen row, scrolled to the middle, as a native picker does. */
function focusChosen(event: Event) {
  event.preventDefault()
  const box = listbox.value
  if (!box) return
  const row =
    box.querySelector<HTMLElement>('[role="option"][aria-selected="true"]') ??
    box.querySelector<HTMLElement>('[role="option"]:not(:disabled)')
  if (!row) return
  box.scrollTop = row.offsetTop - (box.clientHeight - row.offsetHeight) / 2
  row.focus({ preventScroll: true })
}

/**
 * Back to the trigger, also when it never had focus: Safari does not focus a
 * tapped button, and focus would otherwise drop to the page (or out of the
 * sheet the select sits in).
 */
function focusTrigger(event: Event) {
  event.preventDefault()
  root.triggerElement.value?.focus({ preventScroll: true })
}
</script>

<template>
  <template v-if="isPhone">
    <PhoneScope mode="register">
      <div hidden data-slot="select-phone-options">
        <slot />
      </div>
    </PhoneScope>

    <Dialog :open="root.open.value" @update:open="root.onOpenChange">
      <DialogContent
        data-slot="select-content"
        class="flex max-h-[calc(100dvh-6rem-env(safe-area-inset-top)-env(safe-area-inset-bottom))] max-w-[calc(100%-3rem)] flex-col gap-0 p-0"
        :aria-describedby="undefined"
        @open-auto-focus="focusChosen"
        @close-auto-focus="focusTrigger"
      >
        <DialogHeader class="px-6 pt-6 pr-12 pb-3 text-left">
          <DialogTitle>{{ title }}</DialogTitle>
        </DialogHeader>
        <PhoneScope mode="list">
          <div
            ref="listbox"
            role="listbox"
            :aria-label="title"
            class="relative min-h-0 overflow-y-auto overscroll-contain border-t p-2"
          >
            <slot />
          </div>
        </PhoneScope>
      </DialogContent>
    </Dialog>
  </template>

  <SelectPortal v-else>
    <SelectContent
      data-slot="select-content"
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 relative z-50 max-h-(--reka-select-content-available-height) min-w-[8rem] overflow-x-hidden overflow-y-auto rounded-md border shadow-md',
          position === 'popper' &&
            'data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1',
          props.class,
        )
      "
    >
      <SelectScrollUpButton />
      <SelectViewport
        :class="
          cn(
            'p-1',
            position === 'popper' &&
              'h-[var(--reka-select-trigger-height)] w-full min-w-[var(--reka-select-trigger-width)] scroll-my-1',
          )
        "
      >
        <slot />
      </SelectViewport>
      <SelectScrollDownButton />
    </SelectContent>
  </SelectPortal>
</template>
