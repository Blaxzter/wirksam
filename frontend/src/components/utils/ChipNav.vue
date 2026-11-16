<script setup lang="ts">
import { type Component, nextTick, ref, watch } from 'vue'

import ScrollRow from '@/components/utils/ScrollRow.vue'

export interface ChipNavItem {
  label: string
  icon?: Component
}

const props = withDefaults(
  defineProps<{
    items: ChipNavItem[]
    variant?: 'rounded' | 'square'
    stretch?: boolean
  }>(),
  { variant: 'square', stretch: false },
)

const activeIndex = defineModel<number>({ default: 0 })

const itemRefs = ref<(HTMLElement | null)[]>([])

function select(index: number) {
  activeIndex.value = index
}

watch(activeIndex, async () => {
  await nextTick()
  itemRefs.value[activeIndex.value]?.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest',
    inline: 'center',
  })
})
</script>

<template>
  <ScrollRow content-class="gap-2">
    <button
      v-for="(item, index) in props.items"
      :key="index"
      :ref="(el) => (itemRefs[index] = el as HTMLElement)"
      @click="select(index)"
      class="flex items-center justify-center gap-1.5 px-3.5 py-2 text-sm font-medium transition-all duration-200"
      :class="[
        stretch ? 'grow shrink-0 whitespace-nowrap' : 'shrink-0',
        variant === 'rounded' ? 'rounded-full' : 'rounded-lg',
        activeIndex === index
          ? 'bg-primary text-primary-foreground shadow-sm'
          : 'bg-muted text-muted-foreground hover:bg-muted/80',
      ]"
    >
      <component v-if="item.icon" :is="item.icon" class="h-3.5 w-3.5" />
      {{ item.label }}
    </button>
  </ScrollRow>
</template>
