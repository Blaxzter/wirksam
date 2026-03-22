<script setup lang="ts">
import { useColorMode } from '@vueuse/core'
import { MoonIcon, SunIcon } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'

withDefaults(
  defineProps<{
    variant?: 'ghost' | 'outline' | 'default'
    size?: 'sm' | 'default' | 'icon'
  }>(),
  {
    variant: 'ghost',
    size: 'sm',
  },
)

const mode = useColorMode()

function toggle() {
  mode.value = mode.value === 'dark' ? 'light' : 'dark'
}
</script>

<template>
  <Button
    :variant="variant"
    :size="size"
    @click="toggle"
    :aria-label="mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
  >
    <SunIcon v-if="mode === 'dark'" class="h-4 w-4" />
    <MoonIcon v-else class="h-4 w-4" />
  </Button>
</template>
