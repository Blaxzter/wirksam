<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'

import { reactiveOmit } from '@vueuse/core'
import type { DrawerContentEmits, DrawerContentProps } from 'reka-ui'
import { DrawerContent, DrawerHandle, DrawerPortal, useForwardPropsEmits } from 'reka-ui'

import { useFocusReturn } from '@/composables/useFocusReturn'

import { cn } from '@/lib/utils'

import DrawerOverlay from './DrawerOverlay.vue'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<
  DrawerContentProps & {
    class?: HTMLAttributes['class']
    /**
     * Render above another open drawer.
     *
     * Not stock shadcn — it mirrors the prop `DialogContent` already carries,
     * because `GlobalDialog` opens on top of whatever asked it a question. Both
     * shells sit at `z-50`, so without this the second sheet's own overlay
     * lands over the first sheet's buttons and neither can be pressed.
     */
    priority?: boolean
  }
>()
const emits = defineEmits<DrawerContentEmits>()

const delegatedProps = reactiveOmit(props, 'class', 'priority')

const forwarded = useForwardPropsEmits(delegatedProps, emits)

/*
 * Not stock shadcn: reka's Drawer hands focus back only to a DrawerTrigger,
 * and our sheets open through v-model, so closing one dropped focus to
 * <body>. The opener is noted before a parent's handler can move focus into
 * the sheet, and restored after the parent's own close handler had its say.
 */
const focusReturn = useFocusReturn()

function onOpenAutoFocus(event: Event) {
  focusReturn.remember()
  emits('openAutoFocus', event)
}

function onCloseAutoFocus(event: Event) {
  emits('closeAutoFocus', event)
  focusReturn.restore(event)
}
</script>

<template>
  <DrawerPortal>
    <DrawerOverlay :class="priority ? '!z-60' : undefined" />
    <DrawerContent
      data-slot="drawer-content"
      v-bind="{ ...$attrs, ...forwarded, onOpenAutoFocus, onCloseAutoFocus }"
      :class="
        cn(
          'group/drawer-content bg-background fixed z-50 flex h-auto flex-col',
          priority && 'z-60',
          'will-change-transform transform-[translate3d(var(--drawer-swipe-movement-x,0px),var(--drawer-swipe-movement-y,0px),0)]',
          'transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] data-swiping:duration-0 data-swiping:select-none',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[swipe-direction=up]:inset-x-0 data-[swipe-direction=up]:top-0 data-[swipe-direction=up]:mb-24 data-[swipe-direction=up]:max-h-[80vh] data-[swipe-direction=up]:rounded-b-lg data-[swipe-direction=up]:data-[state=open]:slide-in-from-top data-[swipe-direction=up]:data-[state=closed]:slide-out-to-top',
          'data-[swipe-direction=down]:inset-x-0 data-[swipe-direction=down]:bottom-0 data-[swipe-direction=down]:mt-24 data-[swipe-direction=down]:max-h-[80vh] data-[swipe-direction=down]:rounded-t-lg data-[swipe-direction=down]:data-[state=open]:slide-in-from-bottom data-[swipe-direction=down]:data-[state=closed]:slide-out-to-bottom',
          'data-[swipe-direction=right]:inset-y-0 data-[swipe-direction=right]:right-0 data-[swipe-direction=right]:w-3/4 data-[swipe-direction=right]:sm:max-w-sm data-[swipe-direction=right]:data-[state=open]:slide-in-from-right data-[swipe-direction=right]:data-[state=closed]:slide-out-to-right',
          'data-[swipe-direction=left]:inset-y-0 data-[swipe-direction=left]:left-0 data-[swipe-direction=left]:w-3/4 data-[swipe-direction=left]:sm:max-w-sm data-[swipe-direction=left]:data-[state=open]:slide-in-from-left data-[swipe-direction=left]:data-[state=closed]:slide-out-to-left',
          props.class,
        )
      "
    >
      <DrawerHandle
        class="bg-muted mx-auto mt-4 hidden h-2 w-[100px] shrink-0 rounded-full group-data-[swipe-direction=down]/drawer-content:block"
      />
      <slot />
    </DrawerContent>
  </DrawerPortal>
</template>
