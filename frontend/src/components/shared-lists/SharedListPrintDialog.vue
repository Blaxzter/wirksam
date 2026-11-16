<script setup lang="ts">
/**
 * Asked once before a notice is printed with a new shared list: what the list
 * will be (its title, every shift still to come, the wizard's defaults) and
 * which tasks print without a QR code. "Anlegen und drucken" creates it,
 * "Erst anpassen" opens the wizard instead.
 *
 * When nothing can go on a list (an unpublished or team-only task, no free
 * place ahead, too many tasks), it says why and offers the sheet without a QR
 * code. A dialog on a wide screen, a sheet on a phone; focus goes back to
 * whatever opened it, or to `returnFocus` on a page where nothing did.
 */
import { computed, shallowRef, watch } from 'vue'

import { useI18n } from 'vue-i18n'

import type { NoticeDialog } from '@/composables/useSharedListPrint'

import { Button } from '@/components/ui/button'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import SharedListSettingsSummary from '@/components/shared-lists/SharedListSettingsSummary.vue'

import { type LeftOutTask, noticeListBody } from '@/lib/shared-list-print'
import { MAX_TASKS } from '@/lib/shared-list-selection'

const props = defineProps<{
  /** What to ask or explain; none closes the dialog. */
  dialog: NoticeDialog | null
  /** The list is being created. */
  busy?: boolean
  /** Moves focus once the dialog has closed, when no button opened it. */
  returnFocus?: () => void
}>()

const emit = defineEmits<{
  create: []
  customize: []
  /** Print the sheet without a QR code. */
  plain: []
  close: []
}>()

const { t } = useI18n()

const open = computed(() => props.dialog !== null)

/** Kept while the dialog closes, so its content does not change mid-animation. */
const shown = shallowRef<NoticeDialog | null>(props.dialog)
watch(
  () => props.dialog,
  (next) => {
    if (next) shown.value = next
  },
)

/** The settings a new list gets, as its summary reads them. */
const settings = computed(() =>
  shown.value?.kind === 'create'
    ? { ...noticeListBody(shown.value.title, shown.value.taskIds), closes_at: null }
    : null,
)

const leftOut = computed<LeftOutTask[]>(() =>
  shown.value && shown.value.kind !== 'task' ? shown.value.leftOut : [],
)

function onCloseAutoFocus(event: Event) {
  if (!props.returnFocus) return
  event.preventDefault()
  props.returnFocus()
}

const explanation = computed(() => {
  const dialog = shown.value
  if (dialog?.kind === 'task') return t(`print.notice.problem.${dialog.problem}`)
  if (dialog?.kind === 'event') {
    return dialog.reason === 'too_many'
      ? t('print.notice.problem.too_many', { max: MAX_TASKS, count: dialog.offered })
      : t(`print.notice.problem.${dialog.reason}`)
  }
  return ''
})
</script>

<template>
  <ResponsiveDialog :open="open" @update:open="(value) => !value && emit('close')">
    <ResponsiveDialogContent
      dialog-class="sm:max-w-lg"
      data-testid="shared-list-print-dialog"
      @close-auto-focus="onCloseAutoFocus"
    >
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="text-lg leading-tight font-bold">
          {{
            shown?.kind === 'create'
              ? t('print.notice.create.title')
              : shown?.kind === 'event'
                ? t('print.notice.problem.titleEvent')
                : t('print.notice.problem.title')
          }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription>
          {{ shown?.kind === 'create' ? t('print.notice.create.text') : explanation }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="grid content-start gap-4 pb-5 text-sm">
        <SharedListSettingsSummary v-if="shown?.kind === 'create' && settings" :list="settings">
          <dt class="text-muted-foreground">{{ t('print.notice.create.titleLabel') }}</dt>
          <dd class="mb-2 font-medium break-words sm:mb-0" data-testid="shared-list-print-title">
            {{ shown.title }}
          </dd>
          <dt class="text-muted-foreground">{{ t('print.notice.create.shiftsLabel') }}</dt>
          <dd class="mb-2 sm:mb-0">
            {{
              t('print.notice.create.shifts', { count: shown.taskIds.length }, shown.taskIds.length)
            }}
          </dd>
        </SharedListSettingsSummary>

        <div v-if="leftOut.length" class="grid gap-1.5" data-testid="shared-list-print-left-out">
          <p class="font-medium">{{ t('print.notice.leftOut.title') }}</p>
          <ul class="grid list-disc gap-1 pl-5">
            <li v-for="task in leftOut" :key="task.id">
              {{ t(`print.notice.leftOut.${task.problem}`, { name: task.name }) }}
            </li>
          </ul>
        </div>

        <p class="text-muted-foreground">
          {{
            shown?.kind === 'create'
              ? t('print.notice.create.later')
              : t('print.notice.problem.paper')
          }}
        </p>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter>
        <template v-if="shown?.kind === 'create'">
          <Button
            variant="outline"
            class="max-md:h-11"
            data-testid="shared-list-print-customize"
            @click="emit('customize')"
          >
            {{ t('print.notice.create.customize') }}
          </Button>
          <Button
            class="max-md:h-11 aria-disabled:opacity-50"
            :aria-disabled="busy || undefined"
            data-testid="shared-list-print-create"
            @click="!busy && emit('create')"
          >
            {{ busy ? t('common.states.saving') : t('print.notice.create.confirm') }}
          </Button>
        </template>
        <template v-else>
          <Button variant="outline" class="max-md:h-11" @click="emit('close')">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button class="max-md:h-11" data-testid="shared-list-print-plain" @click="emit('plain')">
            {{ t('print.notice.problem.print') }}
          </Button>
        </template>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
