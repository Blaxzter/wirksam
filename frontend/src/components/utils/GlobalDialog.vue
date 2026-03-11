<template>
  <Dialog v-model:open="dialogStore.dialog.isOpen">
    <DialogContent class="sm:max-w-md" priority>
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <component :is="titleIcon" v-if="titleIcon" class="h-5 w-5" :class="titleIconClass" />
          {{ dialogTitle }}
        </DialogTitle>
        <DialogDescription class="text-left">
          {{ dialogStore.dialog.text }}
        </DialogDescription>
      </DialogHeader>

      <DialogFooter class="sm:justify-start">
        <template v-if="dialogStore.dialog.type === 'confirm'">
          <Button
            v-if="dialogStore.dialog.onCancel"
            variant="outline"
            @click="handleCancel"
            class="flex items-center gap-2"
          >
            <component :is="cancelIcon" v-if="cancelIcon" class="h-4 w-4" />
            {{ cancelText }}
          </Button>
          <Button
            v-if="dialogStore.dialog.onConfirm"
            :variant="dialogStore.dialog.variant"
            @click="handleConfirm"
            class="flex items-center gap-2"
          >
            <component :is="confirmIcon" v-if="confirmIcon" class="h-4 w-4" />
            {{ confirmText }}
          </Button>
        </template>

        <template v-else>
          <Button
            v-if="dialogStore.dialog.onConfirm"
            :variant="dialogStore.dialog.variant"
            @click="handleConfirm"
            class="flex items-center gap-2"
          >
            <component :is="confirmIcon" v-if="confirmIcon" class="h-4 w-4" />
            {{ okText }}
          </Button>
        </template>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { AlertCircleIcon, AlertTriangleIcon, CheckIcon, InfoIcon, XIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { useDialogStore } from '@/stores/dialog'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const { t } = useI18n()
const dialogStore = useDialogStore()

// Icon mappings
const iconMap = {
  check: CheckIcon,
  x: XIcon,
  'alert-triangle': AlertTriangleIcon,
  info: InfoIcon,
  'alert-circle': AlertCircleIcon,
}

// Computed properties for dynamic content
const dialogTitle = computed(() => {
  const config = dialogStore.dialog
  if (config.title) return config.title

  return t(`common.dialog.${config.type}.title`)
})

const confirmText = computed(() => {
  const config = dialogStore.dialog
  if (config.confirmText) return config.confirmText

  return t('common.dialog.confirm.confirmText')
})

const cancelText = computed(() => {
  const config = dialogStore.dialog
  if (config.cancelText) return config.cancelText

  return t('common.dialog.confirm.cancelText')
})

const okText = computed(() => {
  const config = dialogStore.dialog
  return t(`common.dialog.${config.type}.okText`)
})

// Icon computations
const confirmIcon = computed(() => {
  const config = dialogStore.dialog
  if (config.confirmIcon && iconMap[config.confirmIcon as keyof typeof iconMap]) {
    return iconMap[config.confirmIcon as keyof typeof iconMap]
  }

  // Default icons based on type and variant
  if (config.type === 'confirm') {
    return config.variant === 'destructive' ? AlertTriangleIcon : CheckIcon
  }
  return CheckIcon
})

const cancelIcon = computed(() => {
  const config = dialogStore.dialog
  if (config.cancelIcon && iconMap[config.cancelIcon as keyof typeof iconMap]) {
    return iconMap[config.cancelIcon as keyof typeof iconMap]
  }

  return XIcon
})

const titleIcon = computed(() => {
  const config = dialogStore.dialog

  switch (config.type) {
    case 'alert':
      return config.variant === 'destructive' ? AlertCircleIcon : AlertTriangleIcon
    case 'info':
      return InfoIcon
    default:
      return null
  }
})

const titleIconClass = computed(() => {
  const config = dialogStore.dialog

  switch (config.type) {
    case 'alert':
      return config.variant === 'destructive' ? 'text-destructive' : 'text-yellow-600'
    case 'info':
      return 'text-blue-600'
    default:
      return ''
  }
})

// Event handlers
const handleConfirm = async () => {
  const onConfirm = dialogStore.dialog.onConfirm
  if (onConfirm) {
    await onConfirm()
  }
}

const handleCancel = async () => {
  const onCancel = dialogStore.dialog.onCancel
  if (onCancel) {
    await onCancel()
  }
}
</script>
