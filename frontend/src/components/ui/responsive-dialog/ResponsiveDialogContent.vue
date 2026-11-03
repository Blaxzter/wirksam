<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { DialogContent } from '@/components/ui/dialog'
import { DrawerClose, DrawerContent } from '@/components/ui/drawer'

import { cn } from '@/lib/utils'

import { useResponsiveDialog } from './utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
  /** Applied to the centred-dialog branch only. */
  dialogClass?: HTMLAttributes['class']
  /** Applied to the bottom-drawer branch only. */
  drawerClass?: HTMLAttributes['class']
  /** Stack above another open dialog. Honoured by both shells. */
  priority?: boolean
  /**
   * Bottom-drawer branch only: open without focusing the first field. A
   * focused number or search field brings up the phone's keyboard (or a
   * combobox's list) over the sheet's own buttons, which is wrong when the
   * usual answer is the preset one. Focus goes to the sheet itself instead.
   */
  keepKeyboardClosed?: boolean
}>()

const { isMobile } = useResponsiveDialog()
const { t } = useI18n()

function onDrawerOpenAutoFocus(event: Event) {
  if (!props.keepKeyboardClosed) return
  event.preventDefault()
  ;(event.target as HTMLElement | null)?.focus?.({ preventScroll: true })
}
</script>

<template>
  <!--
    `p-0` / `gap-0` on both branches on purpose: Header, Body and Footer own
    their own padding so the two shells measure the same, and so Body can be the
    only thing that scrolls.
  -->
  <DrawerContent
    v-if="isMobile"
    v-bind="$attrs"
    :priority="priority"
    :class="cn('gap-0 p-0 focus:outline-none', props.class, drawerClass)"
    @open-auto-focus="onDrawerOpenAutoFocus"
  >
    <slot />
    <!--
      The drag handle and swiping down already close this, but neither is
      reachable without a pointer, so the drawer keeps a real close button too.
      Positioned to match the one `DialogContent` bakes in — and rendered last
      for the same reason it is there, so opening the sheet settles focus on the
      first real control rather than on Close.

      `focus-visible` rather than `focus`: reka moves focus here on open, and a
      plain `focus:` ring would draw a box around the ✕ every time the sheet is
      opened by touch.

      The glyph is 16 px; the invisible 44 px square centred on it (`after:`)
      is what a thumb actually has to hit, as in `DialogContent`.
    -->
    <DrawerClose
      class="ring-offset-background focus-visible:ring-ring absolute top-4 right-4 rounded-xs opacity-70 transition-opacity after:absolute after:top-1/2 after:left-1/2 after:size-11 after:-translate-x-1/2 after:-translate-y-1/2 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0"
    >
      <X class="size-4" />
      <span class="sr-only">{{ t('common.actions.close') }}</span>
    </DrawerClose>
  </DrawerContent>

  <DialogContent
    v-else
    v-bind="$attrs"
    :priority="priority"
    :class="cn('flex max-h-[85vh] flex-col gap-0 p-0', props.class, dialogClass)"
  >
    <slot />
  </DialogContent>
</template>
