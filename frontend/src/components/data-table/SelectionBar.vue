<script setup lang="ts">
/**
 * What can be done with the rows ticked in a table: a bar that says how many
 * are selected, offers the actions and a way to clear the selection, and can
 * turn into an inline confirmation.
 *
 * Place it after the table, inside the same section: it is sticky, so it stays
 * in view at the bottom of the screen while that section is (above the phone's
 * bottom navigation), and never covers the sidebar. It renders nothing while
 * nothing is selected.
 *
 * On a phone the actions fold into one "Actions" menu and "Clear selection"
 * becomes an icon, so the bar stays one line instead of a block of buttons.
 * An action picked from the menu is reported once the menu has closed and its
 * button has focus again (`useMenuAction`), so a dialog it opens hands focus
 * back there. `confirming` swaps the bar's content for the `confirm` slot,
 * which is announced and focused; when it closes, focus goes back to the
 * control that started it.
 *
 * Its buttons stay focusable while they cannot be used (`aria-disabled`): a
 * disabled button drops focus to <body>, and so would the bar itself when it
 * goes, which is why `focusOnLeave` names where focus goes then.
 */
import { type Component, nextTick, useTemplateRef, watch } from 'vue'

import { ChevronDown, X } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { useMenuAction } from '@/composables/useMenuAction'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export interface SelectionAction {
  id: string
  label: string
  icon?: Component
  disabled?: boolean
  /** Ends or removes something; drawn in the danger colour. */
  destructive?: boolean
}

const props = withDefaults(
  defineProps<{
    /** How many rows are selected. Nothing renders at 0. */
    count: number
    actions?: readonly SelectionAction[]
    /** Shows the `confirm` slot in place of the message and the actions. */
    confirming?: boolean
    /** Names the region; "Selection" unless given. */
    label?: string
    /** `dialog` sticks to the bottom of a scrolling dialog instead of the screen. */
    placement?: 'page' | 'dialog'
    /**
     * Where focus goes when the selection empties while focus is in the bar,
     * which then disappears: usually the table's first checkbox.
     */
    focusOnLeave?: () => HTMLElement | null | undefined
  }>(),
  {
    actions: () => [],
    confirming: false,
    label: undefined,
    placement: 'page',
    focusOnLeave: undefined,
  },
)

const emit = defineEmits<{
  action: [id: string]
  clear: []
}>()

defineSlots<{
  /** Replaces "{n} selected". */
  message?: () => unknown
  /** More controls, after the actions. */
  default?: () => unknown
  /** The question and its buttons while `confirming`. */
  confirm?: () => unknown
}>()

const { t } = useI18n()
const menu = useMenuAction()
const wide = useMediaQuery('(min-width: 640px)')

const bar = useTemplateRef<HTMLElement>('bar')
const confirmBox = useTemplateRef<HTMLElement>('confirmBox')

/** The control that started the last action, to give focus back to after a confirmation. */
let startedFrom: string | null = null

function run(action: SelectionAction, via: string) {
  if (action.disabled) return
  startedFrom = via
  emit('action', action.id)
}

function pick(action: SelectionAction) {
  menu.after(() => run(action, 'menu'))
}

watch(
  () => props.confirming,
  async (now, before) => {
    await nextTick()
    if (now) {
      confirmBox.value?.focus()
    } else if (before) {
      const back =
        (startedFrom &&
          bar.value?.querySelector<HTMLElement>(`[data-started-from="${startedFrom}"]`)) ||
        bar.value?.querySelector<HTMLElement>('button:not([aria-disabled="true"])')
      back?.focus()
    }
  },
)

// Before the bar leaves the page (`flush: 'pre'` runs ahead of the update), so
// it can still tell whether it held focus.
watch(
  () => props.count > 0,
  async (shown) => {
    if (shown || !bar.value?.contains(document.activeElement)) return
    await nextTick()
    props.focusOnLeave?.()?.focus()
  },
  { flush: 'pre' },
)

const PLACEMENT_CLASS = {
  page: 'bottom-[calc(5rem+env(safe-area-inset-bottom))] md:bottom-4',
  dialog: 'bottom-0',
}
</script>

<template>
  <div
    v-if="props.count > 0"
    ref="bar"
    role="region"
    :aria-label="props.label ?? t('common.selection.region')"
    class="sticky z-40 flex min-h-14 items-center gap-2 rounded-xl border bg-popover px-3 py-2 text-popover-foreground shadow-lg"
    :class="PLACEMENT_CLASS[props.placement]"
    data-testid="selection-bar"
  >
    <div
      v-if="props.confirming"
      ref="confirmBox"
      role="alert"
      tabindex="-1"
      class="flex w-full flex-wrap items-center gap-x-3 gap-y-2 outline-none"
      data-testid="selection-confirm"
    >
      <slot name="confirm" />
    </div>
    <template v-else>
      <p class="min-w-0 flex-1 text-sm leading-snug" data-testid="selection-message">
        <slot name="message">
          <span class="font-semibold tabular-nums">{{
            t('common.selection.count', { count: props.count }, props.count)
          }}</span>
        </slot>
      </p>

      <template v-if="wide">
        <Button
          v-for="action in props.actions"
          :key="action.id"
          size="sm"
          :variant="action.destructive ? 'destructive' : 'outline'"
          class="aria-disabled:opacity-50"
          :aria-disabled="action.disabled || undefined"
          :data-started-from="action.id"
          :data-testid="`selection-action-${action.id}`"
          @click="run(action, action.id)"
        >
          <component :is="action.icon" v-if="action.icon" aria-hidden="true" />
          {{ action.label }}
        </Button>
      </template>
      <Button
        v-else-if="props.actions.length === 1"
        size="sm"
        :variant="props.actions[0].destructive ? 'destructive' : 'outline'"
        class="aria-disabled:opacity-50"
        :aria-disabled="props.actions[0].disabled || undefined"
        :data-started-from="props.actions[0].id"
        :data-testid="`selection-action-${props.actions[0].id}`"
        @click="run(props.actions[0], props.actions[0].id)"
      >
        <component :is="props.actions[0].icon" v-if="props.actions[0].icon" aria-hidden="true" />
        {{ props.actions[0].label }}
      </Button>
      <DropdownMenu v-else-if="props.actions.length > 1">
        <DropdownMenuTrigger as-child>
          <Button
            size="sm"
            variant="outline"
            data-started-from="menu"
            data-testid="selection-actions"
          >
            {{ t('common.selection.actions') }}
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" @close-auto-focus="menu.onCloseAutoFocus">
          <DropdownMenuItem
            v-for="action in props.actions"
            :key="action.id"
            :disabled="action.disabled"
            :variant="action.destructive ? 'destructive' : 'default'"
            :data-testid="`selection-action-${action.id}`"
            @select="pick(action)"
          >
            <component :is="action.icon" v-if="action.icon" aria-hidden="true" />
            {{ action.label }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <slot />

      <Button
        v-if="wide"
        size="sm"
        variant="ghost"
        data-testid="selection-clear"
        @click="emit('clear')"
      >
        {{ t('common.selection.clear') }}
      </Button>
      <Button
        v-else
        size="icon"
        variant="ghost"
        :aria-label="t('common.selection.clear')"
        data-testid="selection-clear"
        @click="emit('clear')"
      >
        <X aria-hidden="true" />
      </Button>
    </template>
  </div>
</template>
