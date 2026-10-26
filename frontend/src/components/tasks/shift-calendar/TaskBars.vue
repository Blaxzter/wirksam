<script setup lang="ts">
import { Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { CalendarTask, TaskBar } from './types'

defineProps<{
  bars: TaskBar[]
  hoveredTaskId: string | null
  topOffset?: number
}>()

const emit = defineEmits<{
  navigateTask: [task: CalendarTask]
  hover: [eventId: string | null]
}>()

const { t } = useI18n()
</script>

<template>
  <div
    v-for="bar in bars"
    :key="'ebar-' + bar.task.id"
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
        bar.isStart && bar.isEnd
          ? 'rounded'
          : bar.isStart
            ? 'rounded-l'
            : bar.isEnd
              ? 'rounded-r'
              : '',
        bar.task.status === 'published'
          ? hoveredTaskId === bar.task.id
            ? 'bg-primary/25 text-primary'
            : 'bg-primary/15 text-primary'
          : hoveredTaskId === bar.task.id
            ? 'bg-muted-foreground/25 text-muted-foreground'
            : 'bg-muted text-muted-foreground',
      ]"
      :style="{
        marginLeft: bar.isStart ? '0' : '-4px',
        paddingLeft: bar.isStart ? undefined : '6px',
        width:
          !bar.isStart && !bar.isEnd
            ? 'calc(100% + 8px)'
            : !bar.isStart
              ? 'calc(100% + 4px)'
              : !bar.isEnd
                ? 'calc(100% + 4px)'
                : undefined,
      }"
      :aria-label="t('duties.tasks.calendar.openTask', { name: bar.task.name })"
      @mouseenter="emit('hover', bar.task.id)"
      @mouseleave="emit('hover', null)"
      @click="emit('navigateTask', bar.task)"
    >
      <span v-if="bar.isStart || bar.startCol === 0" class="truncate">
        <Lock
          v-if="bar.task.locked_by_team"
          class="mr-0.5 inline size-3 align-[-2px]"
          role="img"
          :aria-label="t('teamLocks.badge.locked', { name: bar.task.team_name ?? '' })"
        />{{ bar.task.name }}</span
      >
    </button>
  </div>
</template>
