<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'

import { reactiveOmit } from '@vueuse/core'
import type { CalendarCellTriggerProps } from 'reka-ui'
import { CalendarCellTrigger, useForwardProps } from 'reka-ui'

import { buttonVariants } from '@/components/ui/button'

import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<CalendarCellTriggerProps & { class?: HTMLAttributes['class'] }>(),
  {
    // Keep reka-ui's own default of `div`. It renders `role="button"` and drives
    // the grid with a roving tabindex: 0 on the focused day, -1 on the other
    // days of the month, and *no tabindex attribute at all* on days that are
    // disabled or belong to a neighbouring month. A native <button> is focusable
    // without a tabindex, so rendering one — as the shadcn-vue port does — turned
    // every adjacent-month and disabled day back into a tab stop (12 of them in a
    // plain month view instead of 1).
    //
    // That is not just noisy: it wedges the tab. reka's arrow-key handler looks
    // for the neighbouring day with `[data-value=…]:not([data-outside-view])`,
    // and a day next to an adjacent-month day never matches — so it pages the
    // calendar and retries through `nextTick` with the same origin day, forever,
    // starving the microtask queue (#149). DateRangePicker's
    // RangeCalendarCellTrigger already leaves this at `div` and is unaffected.
    as: 'div',
  },
)

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <CalendarCellTrigger
    data-slot="calendar-cell-trigger"
    :class="
      cn(
        buttonVariants({ variant: 'ghost' }),
        'size-8 p-0 font-normal aria-selected:opacity-100 cursor-pointer',
        '[&[data-today]:not([data-selected])]:bg-accent [&[data-today]:not([data-selected])]:text-accent-foreground',
        // Selected
        'data-[selected]:bg-primary data-[selected]:text-primary-foreground data-[selected]:opacity-100 data-[selected]:hover:bg-primary data-[selected]:hover:text-primary-foreground data-[selected]:focus:bg-primary data-[selected]:focus:text-primary-foreground',
        // Disabled
        'data-[disabled]:text-muted-foreground data-[disabled]:opacity-50',
        // Unavailable
        'data-[unavailable]:text-destructive-foreground data-[unavailable]:line-through',
        // Outside months
        'data-[outside-view]:text-muted-foreground',
        props.class,
      )
    "
    v-bind="forwardedProps"
  >
    <slot />
  </CalendarCellTrigger>
</template>
