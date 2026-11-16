<script setup lang="ts">
/**
 * A checkbox that can also be half ticked, "some of these", and looks it: a
 * filled box with a dash. The stock one draws its tick on an empty box then,
 * which reads as "all of them".
 */
import { Check, Minus } from '@lucide/vue'

import { Checkbox } from '@/components/ui/checkbox'

defineProps<{ modelValue: boolean | 'indeterminate' }>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean | 'indeterminate'] }>()
</script>

<template>
  <Checkbox
    :model-value="modelValue"
    class="data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground"
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <Minus v-if="modelValue === 'indeterminate'" class="size-3.5" />
    <Check v-else class="size-3.5" />
  </Checkbox>
</template>
