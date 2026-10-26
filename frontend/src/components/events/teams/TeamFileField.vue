<script setup lang="ts">
import { ref } from 'vue'

import { FileText, Paperclip, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import Button from '@/components/ui/button/Button.vue'

import { documentProblem } from '@/components/events/teams/teamDocuments'
import { DOCUMENT_TYPES } from '@/components/events/teams/teamHelpers'

/**
 * One file slot for one requirement: "Attach a file", or the attached file
 * with Replace and Remove. The parent decides what picking means (keep it for
 * later, or upload it now); a file of the wrong kind or size never leaves
 * here.
 */
defineProps<{
  /** Name of the file in this slot, if any. */
  filename?: string | null
  /** Accessible name of the slot, e.g. the requirement's label. */
  label: string
  busy?: boolean
  testid?: string
}>()

const emit = defineEmits<{ choose: [file: File]; remove: [] }>()

const { t } = useI18n()
const input = ref<HTMLInputElement | null>(null)

function onChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return
  const problem = documentProblem(file)
  if (problem === 'type') toast.error(t('teams.join.fileType'))
  else if (problem === 'size') toast.error(t('teams.join.fileTooLarge'))
  else emit('choose', file)
}
</script>

<template>
  <div class="flex min-w-0 flex-wrap items-center gap-2" :data-testid="testid">
    <input
      ref="input"
      type="file"
      class="sr-only"
      tabindex="-1"
      :accept="DOCUMENT_TYPES.join(',')"
      :aria-label="t('teams.join.attachFor', { label })"
      @change="onChange"
    />
    <template v-if="filename">
      <span class="bg-muted inline-flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs">
        <FileText class="size-3.5 shrink-0" />
        <span class="truncate">{{ filename }}</span>
      </span>
      <Button
        variant="ghost"
        size="sm"
        :disabled="busy"
        :aria-label="t('teams.join.replaceFor', { label })"
        @click="input?.click()"
      >
        {{ t('teams.join.replaceFile') }}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        class="text-muted-foreground hover:text-destructive size-8"
        :disabled="busy"
        :aria-label="t('teams.join.removeFileFor', { label })"
        @click="emit('remove')"
      >
        <X class="size-4" />
      </Button>
    </template>
    <Button
      v-else
      variant="outline"
      size="sm"
      :disabled="busy"
      :aria-label="t('teams.join.attachFor', { label })"
      @click="input?.click()"
    >
      <Paperclip class="mr-1.5 size-3.5" />
      {{ t('teams.join.attach') }}
    </Button>
  </div>
</template>
