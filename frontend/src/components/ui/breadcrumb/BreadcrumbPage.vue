<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <span
    data-slot="breadcrumb-page"
    role="link"
    aria-disabled="true"
    aria-current="page"
    :class="cn('text-foreground font-normal select-none max-w-[200px] truncate', props.class)"
  >
    <slot />
  </span>
</template>
