<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { ScrollArea } from '@/components/ui/scroll-area'

import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <ScrollArea
    data-slot="sidebar-content"
    data-sidebar="content"
    :class="
      cn(
        'min-h-0 flex-1 group-data-[collapsible=icon]:[&_[data-slot=scroll-area-viewport]]:overflow-hidden group-data-[collapsible=icon]:[&_[data-slot=scroll-area-scrollbar]]:hidden',
        props.class,
      )
    "
  >
    <div class="flex min-h-0 flex-1 flex-col gap-2">
      <slot />
    </div>
  </ScrollArea>
</template>
