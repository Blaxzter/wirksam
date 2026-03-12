<script setup lang="ts">
import { TriangleAlert, X } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'

defineProps<{
  message: string
  actionLabel: string
  dismissLabel: string
  onAction: () => void
}>()

const emit = defineEmits<{
  closeToast: []
}>()

function handleAction(onAction: () => void) {
  onAction()
  emit('closeToast')
}
</script>

<template>
  <div
    class="flex w-[var(--width)] flex-col gap-2.5 rounded-lg border border-border bg-background p-4 shadow-lg"
  >
    <div class="flex items-start gap-2.5">
      <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
      <p class="flex-1 text-sm">{{ message }}</p>
      <button
        class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        @click="emit('closeToast')"
      >
        <X class="h-4 w-4" />
      </button>
    </div>
    <div class="flex gap-2 pl-6.5">
      <Button size="xs" @click="handleAction(onAction)">
        {{ actionLabel }}
      </Button>
      <Button size="xs" variant="outline" @click="emit('closeToast')">
        {{ dismissLabel }}
      </Button>
    </div>
  </div>
</template>
