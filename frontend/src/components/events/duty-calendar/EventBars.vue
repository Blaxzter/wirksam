<script setup lang="ts">
import type { EventRead } from '@/client/types.gen'

import type { EventBar } from './types'

defineProps<{
  bars: EventBar[]
  hoveredEventId: string | null
  topOffset?: number
}>()

const emit = defineEmits<{
  navigateEvent: [event: EventRead]
  hover: [eventId: string | null]
}>()
</script>

<template>
  <div
    v-for="bar in bars"
    :key="'ebar-' + bar.event.id"
    class="absolute z-10 hidden sm:block"
    :style="{
      top: `${(topOffset ?? 28) + bar.lane * 22}px`,
      left: `calc(${bar.startCol} / 7 * 100% + 4px)`,
      width: `calc(${bar.span} / 7 * 100% - 8px)`,
      height: '20px',
    }"
  >
    <button
      class="flex h-full w-full items-center truncate px-1.5 text-left text-xs font-medium transition-colors"
      :class="[
        bar.isStart && bar.isEnd ? 'rounded' :
        bar.isStart ? 'rounded-l' :
        bar.isEnd ? 'rounded-r' :
        '',
        bar.event.status === 'published'
          ? (hoveredEventId === bar.event.id ? 'bg-primary/25 text-primary' : 'bg-primary/15 text-primary')
          : (hoveredEventId === bar.event.id ? 'bg-muted-foreground/25 text-muted-foreground' : 'bg-muted text-muted-foreground'),
      ]"
      :style="{
        marginLeft: bar.isStart ? '0' : '-4px',
        paddingLeft: bar.isStart ? undefined : '6px',
        width: !bar.isStart && !bar.isEnd ? 'calc(100% + 8px)' :
               !bar.isStart ? 'calc(100% + 4px)' :
               !bar.isEnd ? 'calc(100% + 4px)' :
               undefined,
      }"
      @mouseenter="emit('hover', bar.event.id)"
      @mouseleave="emit('hover', null)"
      @click="emit('navigateEvent', bar.event)"
    >
      <span v-if="bar.isStart || bar.startCol === 0" class="truncate">{{ bar.event.name }}</span>
    </button>
  </div>
</template>
