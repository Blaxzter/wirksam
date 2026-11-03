<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { X } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import type { DialogContentEmits, DialogContentProps } from 'reka-ui'
import { DialogClose, DialogContent, DialogPortal, useForwardPropsEmits } from 'reka-ui'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

import DialogOverlay from './DialogOverlay.vue'

const props = defineProps<
  DialogContentProps & {
    class?: HTMLAttributes['class']
    /** Render at a higher z-index so this dialog stacks above other dialogs */
    priority?: boolean
  }
>()
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = reactiveOmit(props, 'class', 'priority')

const forwarded = useForwardPropsEmits(delegatedProps, emits)

// Not stock shadcn: the close button's label follows the app's language.
const { t } = useI18n()

defineOptions({ inheritAttrs: false })
</script>

<template>
  <DialogPortal>
    <DialogOverlay :class="priority ? '!z-60' : undefined" />
    <DialogContent
      data-slot="dialog-content"
      v-bind="{ ...forwarded, ...$attrs }"
      :class="
        cn(
          'bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border p-6 shadow-lg duration-200 sm:max-w-lg',
          priority && 'z-60',
          props.class,
        )
      "
    >
      <slot />

      <!--
        Not stock shadcn: the ✕ stays a 16 px glyph, but an invisible 44 px
        square centred on it (`after:`) takes the tap, so a thumb need not hit
        the glyph itself. Headers keep `pr-12` clear for it.

        `focus-visible` rather than `focus`, as on the drawer's ✕: a dialog
        with no field opens with focus here, and a plain `focus:` ring drew a
        box around it even when the dialog was opened with the mouse.
      -->
      <DialogClose
        class="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent data-[state=open]:text-muted-foreground absolute top-4 right-4 rounded-xs opacity-70 transition-opacity after:absolute after:top-1/2 after:left-1/2 after:size-11 after:-translate-x-1/2 after:-translate-y-1/2 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"
      >
        <X />
        <span class="sr-only">{{ t('common.actions.close') }}</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
