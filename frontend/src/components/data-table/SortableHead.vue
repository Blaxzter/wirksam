<script setup lang="ts" generic="K extends string">
/**
 * A column header that sorts a server-paginated table by its column.
 *
 * The header cell carries `aria-sort`, which is what a screen reader announces
 * for the column; the button inside is named by the column alone. The arrow
 * shows the direction the column is sorted in, and on an unsorted column, at
 * hover or keyboard focus, the direction a click would start in (`defaultDir`).
 * The direction itself is the caller's: `useTableQuery().setSort(key)`.
 */
import { computed } from 'vue'

import { ArrowDown, ArrowUp, ArrowUpDown } from '@lucide/vue'

import type { SortDir } from '@/composables/useTableQuery'

import { TableHead } from '@/components/ui/table'

const props = withDefaults(
  defineProps<{
    label: string
    sortKey: K
    /** The column the table is sorted by now. */
    activeKey: K
    /** The direction the table is sorted in now. */
    dir: SortDir
    /** The direction this column starts in when chosen. */
    defaultDir?: SortDir
    /** Numbers line up on the right. */
    align?: 'start' | 'end'
  }>(),
  { defaultDir: 'asc', align: 'start' },
)

const emit = defineEmits<{ sort: [key: K] }>()

const active = computed(() => props.activeKey === props.sortKey)
const ariaSort = computed(() =>
  active.value ? (props.dir === 'asc' ? 'ascending' : 'descending') : 'none',
)
const hintIcon = computed(() => (props.defaultDir === 'asc' ? ArrowUp : ArrowDown))
</script>

<template>
  <TableHead :aria-sort="ariaSort" :class="align === 'end' ? 'text-right' : undefined">
    <button
      type="button"
      class="group -mx-2 inline-flex h-8 items-center gap-1.5 rounded-md px-2 font-medium outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
      :class="[align === 'end' ? 'flex-row-reverse' : '', active ? 'text-foreground' : '']"
      :data-testid="`sort-${sortKey}`"
      @click="emit('sort', sortKey)"
    >
      <span>{{ label }}</span>
      <span class="relative inline-flex size-3.5 shrink-0" aria-hidden="true">
        <component :is="dir === 'asc' ? ArrowUp : ArrowDown" v-if="active" class="size-3.5" />
        <template v-else>
          <ArrowUpDown
            class="size-3.5 opacity-40 transition-opacity group-hover:opacity-0 group-focus-visible:opacity-0"
          />
          <component
            :is="hintIcon"
            class="absolute inset-0 size-3.5 opacity-0 transition-opacity group-hover:opacity-70 group-focus-visible:opacity-70"
          />
        </template>
      </span>
    </button>
  </TableHead>
</template>
