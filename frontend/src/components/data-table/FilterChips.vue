<script setup lang="ts" generic="V extends string">
/**
 * A row of toggle buttons that filter a table, exactly one of them on.
 *
 * Each chip says whether it is on with `aria-pressed`, and the row is a named
 * group. On a phone the row scrolls sideways instead of wrapping into a block
 * of buttons; the chip that is on is scrolled into view.
 */
import { nextTick, useTemplateRef, watch } from 'vue'

export interface FilterChip<T extends string = string> {
  value: T
  label: string
  /** How many rows the chip holds; left out, no count is shown. */
  count?: number
  /** `warning` marks a chip that holds things to act on ("Zu tun"). */
  variant?: 'default' | 'warning'
}

const props = defineProps<{
  chips: readonly FilterChip<V>[]
  /** Names the group for a screen reader: what is being filtered. */
  label: string
}>()

const model = defineModel<V>({ required: true })

const list = useTemplateRef<HTMLElement>('list')

function chipClass(chip: FilterChip<V>): string {
  const on = chip.value === model.value
  if (chip.variant === 'warning') {
    return on
      ? 'border-amber-600 bg-amber-600 text-white dark:border-amber-500 dark:bg-amber-500 dark:text-amber-950'
      : 'border-amber-500/60 text-amber-900 hover:bg-amber-100 dark:text-amber-200 dark:hover:bg-amber-950/50'
  }
  return on
    ? 'border-primary bg-primary text-primary-foreground'
    : 'bg-card text-foreground hover:bg-accent hover:text-accent-foreground'
}

watch(model, async () => {
  await nextTick()
  list.value
    ?.querySelector<HTMLElement>('[aria-pressed="true"]')
    ?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
})
</script>

<template>
  <div
    ref="list"
    role="group"
    :aria-label="props.label"
    class="flex min-w-0 gap-2 overflow-x-auto p-1 [scrollbar-width:none] sm:flex-wrap sm:overflow-visible [&::-webkit-scrollbar]:hidden"
  >
    <button
      v-for="chip in props.chips"
      :key="chip.value"
      type="button"
      class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium whitespace-nowrap outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50"
      :class="chipClass(chip)"
      :aria-pressed="chip.value === model"
      :data-testid="`filter-chip-${chip.value}`"
      @click="model = chip.value"
    >
      {{ chip.label }}
      <span
        v-if="chip.count !== undefined"
        class="min-w-5 rounded-full px-1.5 text-xs tabular-nums"
        :class="chip.value === model ? 'bg-black/15 dark:bg-white/20' : 'bg-muted'"
      >
        {{ chip.count }}
      </span>
    </button>
  </div>
</template>
