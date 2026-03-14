<script setup lang="ts">
import { Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Label from '@/components/ui/label/Label.vue'
import { Textarea } from '@/components/ui/textarea'

const open = defineModel<boolean>('open', { required: true })
const reason = defineModel<string>('reason', { default: '' })

defineProps<{
  message: string
  bookingCount?: number
}>()

const emit = defineEmits<{
  confirm: []
}>()

const { t } = useI18n()
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Trash2 class="h-5 w-5 text-destructive" />
          {{ t('common.dialog.confirm.title') }}
        </DialogTitle>
        <DialogDescription class="text-left">
          {{ message }}
        </DialogDescription>
      </DialogHeader>

      <div v-if="bookingCount === undefined || bookingCount > 0" class="space-y-3">
        <p v-if="bookingCount !== undefined && bookingCount > 0" class="text-sm font-medium text-destructive">
          {{ t('duties.deleteDialog.activeBookings', { count: bookingCount }) }}
        </p>
        <p v-else-if="bookingCount === undefined" class="text-sm text-muted-foreground">
          {{ t('duties.deleteDialog.activeBookingsWarning') }}
        </p>
        <div class="space-y-2">
          <Label>{{ t('duties.deleteDialog.reasonLabel') }}</Label>
          <Textarea
            v-model="reason"
            :placeholder="t('duties.deleteDialog.reasonPlaceholder')"
            rows="3"
          />
          <p class="text-xs text-muted-foreground">
            {{ t('duties.deleteDialog.reasonHint') }}
          </p>
        </div>
      </div>

      <DialogFooter class="sm:justify-start">
        <Button variant="outline" @click="open = false">
          {{ t('common.dialog.confirm.cancelText') }}
        </Button>
        <Button variant="destructive" @click="emit('confirm')">
          {{ t('common.dialog.confirm.confirmText') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
