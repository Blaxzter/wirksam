<script setup lang="ts" generic="T extends string">
import type { Component } from 'vue'

/**
 * A short list of choices as cards, each saying what it means: an event's
 * visibility and status, when creating it and in its settings.
 */
export interface EventOption<V extends string> {
  value: V
  label: string
  hint: string
  icon: Component
}

defineProps<{
  options: readonly EventOption<T>[]
  /** Each card's `data-testid` is this plus its value. */
  testidPrefix: string
}>()

const model = defineModel<T>({ required: true })
</script>

<template>
  <div
    class="grid gap-2"
    :class="options.length === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :data-testid="`${testidPrefix}${option.value}`"
      :aria-pressed="model === option.value"
      :class="[
        'rounded-lg border p-3 text-left transition-colors',
        model === option.value
          ? 'border-primary bg-primary/5 ring-2 ring-primary/20'
          : 'hover:border-primary/50',
      ]"
      @click="model = option.value"
    >
      <span class="flex items-center gap-2 text-sm font-medium">
        <component :is="option.icon" class="h-4 w-4" />
        {{ option.label }}
      </span>
      <span class="mt-1 block text-xs text-muted-foreground">{{ option.hint }}</span>
    </button>
  </div>
</template>
