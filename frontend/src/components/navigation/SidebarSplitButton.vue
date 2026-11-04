<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

const props = defineProps<{
  isActive?: boolean
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="
      cn(
        'flex w-full items-stretch rounded-md text-sm text-sidebar-foreground transition-colors',
        'group-data-[collapsible=icon]:size-8! group-data-[collapsible=icon]:overflow-hidden',
        props.isActive && 'bg-black/10 dark:bg-white/10 font-medium text-sidebar-accent-foreground',
        props.class,
      )
    "
  >
    <!-- Navigation area (~3/4) -->
    <slot name="link" />

    <!-- Divider -->
    <div
      :class="
        cn(
          'w-px shrink-0 self-stretch bg-sidebar-border my-1.5',
          'group-data-[collapsible=icon]:hidden',
        )
      "
    />

    <!-- Toggle area (~1/4) -->
    <slot name="action" />
  </div>
</template>
