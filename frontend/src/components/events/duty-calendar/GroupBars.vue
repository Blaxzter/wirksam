<script setup lang="ts">
import type { EventGroupRead } from '@/client/types.gen'

import type { GroupBar } from './types'

defineProps<{
  bars: GroupBar[]
  hoveredGroupId: string | null
  topOffset?: number
}>()

const emit = defineEmits<{
  navigateGroup: [group: EventGroupRead]
  hover: [groupId: string | null]
}>()
</script>

<template>
  <div
    v-for="bar in bars"
    :key="'bar-' + bar.group.id"
    class="absolute z-10 hidden sm:block"
    :style="{
      top: `${(topOffset ?? 28) + bar.lane * 22}px`,
      left: `calc(${bar.startCol} / 7 * 100% + 4px)`,
      width: `calc(${bar.span} / 7 * 100% - 8px)`,
      height: '20px',
    }"
  >
    <button
      class="flex h-full w-full items-center truncate px-1.5 text-left text-xs font-medium text-amber-700 dark:text-amber-400 transition-colors"
      :class="[
        bar.isStart && bar.isEnd ? 'rounded' :
        bar.isStart ? 'rounded-l' :
        bar.isEnd ? 'rounded-r' :
        '',
        hoveredGroupId === bar.group.id ? 'bg-amber-500/25' : 'bg-amber-500/15',
      ]"
      :style="{
        marginLeft: bar.isStart ? '0' : '-4px',
        paddingLeft: bar.isStart ? undefined : '0',
        width: !bar.isStart && !bar.isEnd ? 'calc(100% + 8px)' :
               !bar.isStart ? 'calc(100% + 4px)' :
               !bar.isEnd ? 'calc(100% + 4px)' :
               undefined,
      }"
      @mouseenter="emit('hover', bar.group.id)"
      @mouseleave="emit('hover', null)"
      @click="emit('navigateGroup', bar.group)"
    >
      <span v-if="bar.isStart || bar.startCol === 0" class="truncate">{{ bar.group.name }}</span>
    </button>
  </div>
</template>
