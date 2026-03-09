<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { Clock } from 'lucide-vue-next'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const props = defineProps<{
  modelValue: string
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const open = ref(false)
const listRef = ref<HTMLDivElement>()
const wrapperRef = ref<HTMLDivElement>()
const localValue = ref(props.modelValue)

watch(
  () => props.modelValue,
  (v) => {
    localValue.value = v
  },
)

// Generate time slots in 30-minute increments
const timeSlots = (() => {
  const slots: string[] = []
  for (let h = 0; h < 24; h++) {
    for (let m = 0; m < 60; m += 30) {
      slots.push(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`)
    }
  }
  return slots
})()

function selectTime(time: string) {
  localValue.value = time
  emit('update:modelValue', time)
  open.value = false
}

function onInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  localValue.value = val
  emit('update:modelValue', val)
}

function scrollToSelected() {
  nextTick(() => {
    const el = listRef.value?.querySelector('[data-selected="true"]')
    el?.scrollIntoView({ block: 'center' })
  })
}

function onOpenChange(val: boolean) {
  open.value = val
  if (val) scrollToSelected()
}

function onInteractOutside(e: Event) {
  // Don't close if interaction is within our wrapper (e.g. the input)
  if (wrapperRef.value?.contains(e.target as Node)) {
    e.preventDefault()
  }
}
</script>

<template>
  <Popover :open="open" @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <div
        ref="wrapperRef"
        :class="cn(
          'flex h-8 w-[5.5rem] items-center gap-1.5 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs transition-[color,box-shadow]',
          'focus-within:border-ring focus-within:ring-ring/50 focus-within:ring-[3px]',
        )"
        @click.prevent
      >
        <Clock class="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          type="text"
          :value="localValue"
          :placeholder="placeholder ?? 'HH:MM'"
          class="w-full bg-transparent tabular-nums outline-none placeholder:text-muted-foreground"
          @input="onInput"
          @focus="open = true"
          @click.stop
        />
      </div>
    </PopoverTrigger>
    <PopoverContent
      class="w-28 p-1"
      align="start"
      @open-auto-focus.prevent
      @close-auto-focus.prevent
      @interact-outside="onInteractOutside"
    >
      <div ref="listRef" class="max-h-[12rem] overflow-y-auto">
        <button
          v-for="time in timeSlots"
          :key="time"
          type="button"
          :data-selected="time === modelValue"
          :class="cn(
            'w-full rounded-sm px-2 py-1 text-center text-sm tabular-nums hover:bg-accent hover:text-accent-foreground',
            time === modelValue && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground',
          )"
          @click="selectTime(time)"
        >
          {{ time }}
        </button>
      </div>
    </PopoverContent>
  </Popover>
</template>
