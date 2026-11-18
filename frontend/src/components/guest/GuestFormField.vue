<script setup lang="ts">
/**
 * One field of the public sign-up form: its label (with "optional" where the
 * list makes it so), a hint, and the reason it was refused.
 *
 * The input itself comes through the slot, which hands it the id the label
 * points at and the ids it is described by: the hint, and the error once there
 * is one, so a screen reader reads both when the field takes focus.
 */
import { computed } from 'vue'

import { Label } from '@/components/ui/label'

const props = defineProps<{
  id: string
  label: string
  /** The small "optional" tag after the label. */
  optionalLabel?: string
  hint?: string
  error?: string
}>()

defineSlots<{
  default: (bindings: { id: string; describedBy: string | undefined; invalid: boolean }) => unknown
}>()

const hintId = computed(() => `${props.id}-hint`)
const errorId = computed(() => `${props.id}-error`)
const bindings = computed(() => ({
  id: props.id,
  describedBy:
    [props.hint ? hintId.value : '', props.error ? errorId.value : ''].filter(Boolean).join(' ') ||
    undefined,
  invalid: Boolean(props.error),
}))
</script>

<template>
  <div class="grid gap-1.5">
    <Label :for="id" class="gap-1.5 font-semibold">
      {{ label }}
      <span v-if="optionalLabel" class="text-xs font-normal text-muted-foreground">
        {{ optionalLabel }}
      </span>
    </Label>
    <slot v-bind="bindings" />
    <p v-if="hint" :id="hintId" class="text-xs text-muted-foreground">{{ hint }}</p>
    <p
      v-if="error"
      :id="errorId"
      class="text-sm font-medium text-destructive"
      :data-testid="`${id}-error`"
    >
      {{ error }}
    </p>
  </div>
</template>
