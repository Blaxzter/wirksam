<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

/**
 * Asks for a template's name: when saving a plan as a template ("Save as
 * template…" in the plan menu) and when renaming one of my templates. The
 * input starts with `initialName` every time the dialog opens.
 *
 * `priority` stacks it above another open dialog (renaming from inside "New
 * map").
 */
const props = withDefaults(
  defineProps<{
    title: string
    description: string
    submitLabel: string
    initialName?: string
    saving?: boolean
    priority?: boolean
  }>(),
  { initialName: '', saving: false, priority: false },
)

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ submit: [name: string] }>()

const { t } = useI18n()

const name = ref('')
watch(
  open,
  (isOpen) => {
    if (isOpen) name.value = props.initialName
  },
  { immediate: true },
)

const trimmed = computed(() => name.value.trim())

function submit() {
  if (!trimmed.value || props.saving) return
  emit('submit', trimmed.value)
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent :priority="priority" data-testid="template-name-dialog">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>{{ title }}</ResponsiveDialogTitle>
        <ResponsiveDialogDescription>{{ description }}</ResponsiveDialogDescription>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody class="pb-2">
        <form id="map-editor-template-name" class="space-y-1.5" @submit.prevent="submit">
          <Label for="map-editor-template-name-input">{{ t('mapEditor.templates.name') }}</Label>
          <Input
            id="map-editor-template-name-input"
            v-model="name"
            maxlength="120"
            data-testid="template-name-input"
          />
        </form>
      </ResponsiveDialogBody>
      <ResponsiveDialogFooter>
        <Button variant="outline" @click="open = false">
          {{ t('common.actions.cancel') }}
        </Button>
        <Button
          type="submit"
          form="map-editor-template-name"
          :disabled="!trimmed || saving"
          data-testid="template-name-save"
        >
          {{ submitLabel }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
