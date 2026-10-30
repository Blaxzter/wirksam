<script setup lang="ts">
import { ref, watch } from 'vue'

import { Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import type { TaskRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

import TaskVoucherSettingsFields from './TaskVoucherSettingsFields.vue'

/**
 * "Vouchers…" on the task page, for organisers: the rate is currency and the
 * places that take vouchers are theirs to choose, so people in charge never
 * see this.
 */
const props = defineProps<{ task: TaskRead }>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ saved: [task: TaskRead] }>()

const { t } = useI18n()
const { patch } = useAuthenticatedClient()
const authStore = useAuthStore()

const perShift = ref(0)
const isPoint = ref(false)
const isDesk = ref(false)
const saving = ref(false)

watch(open, (isOpen) => {
  if (!isOpen) return
  perShift.value = props.task.vouchers_per_shift ?? 0
  isPoint.value = props.task.is_voucher_point ?? false
  isDesk.value = props.task.is_voucher_desk ?? false
})

async function save() {
  saving.value = true
  try {
    const res = await patch<{ data: TaskRead }>({
      url: `/tasks/${props.task.id}`,
      body: {
        vouchers_per_shift: perShift.value,
        is_voucher_point: isPoint.value,
        is_voucher_desk: isPoint.value && isDesk.value,
      },
    })
    toast.success(t('vouchers.settings.saved'))
    open.value = false
    emit('saved', res.data)
    // The navigation entry and the dashboard card read the event's counts.
    if (props.task.event_id) void authStore.refreshSelectedEvent(props.task.event_id)
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-md" data-testid="task-voucher-settings-dialog">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="flex items-center gap-2">
          <Ticket class="size-5" />
          {{ t('vouchers.settings.dialogTitle', { task: task.name }) }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription>
          {{ t('vouchers.admin.afterEventHint') }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody class="pb-2">
        <TaskVoucherSettingsFields
          v-model:vouchers-per-shift="perShift"
          v-model:is-point="isPoint"
          v-model:is-desk="isDesk"
          id-prefix="task-vouchers"
        />
      </ResponsiveDialogBody>
      <ResponsiveDialogFooter>
        <Button variant="outline" :disabled="saving" @click="open = false">
          {{ t('common.actions.cancel') }}
        </Button>
        <Button :disabled="saving" data-testid="btn-save-task-vouchers" @click="save">
          {{ t('common.actions.save') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
