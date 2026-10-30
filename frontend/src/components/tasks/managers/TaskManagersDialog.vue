<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import type { TaskRead } from '@/client/types.gen'

import TaskManagersEditor from './TaskManagersEditor.vue'

/**
 * "People in charge…" from the task page: a dialog on desktop, a drawer on
 * phones. Changes are saved as they are made, so there is no Save button.
 */
defineProps<{
  task: TaskRead
}>()

const emit = defineEmits<{ changed: [] }>()

const open = defineModel<boolean>('open', { required: true })

const { t } = useI18n()
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-lg" data-testid="task-managers-dialog">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>
          {{ t('duties.tasks.managers.dialogTitle', { task: task.name }) }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription>
          {{ t('duties.tasks.managers.dialogDescription') }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody class="pb-6">
        <TaskManagersEditor
          v-if="task.event_id"
          :task-id="task.id"
          :event-id="task.event_id"
          :managers="task.managers ?? []"
          @changed="emit('changed')"
        />
      </ResponsiveDialogBody>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
