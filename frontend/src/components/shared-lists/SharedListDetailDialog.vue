<script setup lang="ts">
/**
 * One list in full: its link and QR code, the figures, what it offers, who
 * signed up through it, its settings, and what can be done with it. A dialog
 * on a wide screen, a sheet on a phone.
 *
 * It is open while the page's address names a list (`?list=<id>`), so a
 * reload or a link someone sends opens it again. Rotating and ending ask
 * first. A list the viewer may only read says why.
 */
import { computed, ref, useTemplateRef, watch } from 'vue'

import { Lock, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { type ListAction, useSharedListsStore } from '@/stores/sharedLists'

import { useDialog } from '@/composables/useDialog'

import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import FillBar from '@/components/data-table/FillBar.vue'
import SharedListDetailFooter from '@/components/shared-lists/SharedListDetailFooter.vue'
import SharedListLinkBox from '@/components/shared-lists/SharedListLinkBox.vue'
import SharedListSettingsSummary from '@/components/shared-lists/SharedListSettingsSummary.vue'
import SharedListSignups from '@/components/shared-lists/SharedListSignups.vue'
import SharedListStatusBadge from '@/components/shared-lists/SharedListStatusBadge.vue'
import { useSharedListText } from '@/components/shared-lists/sharedListText'
import { canManageList, useSharedListActions } from '@/components/shared-lists/useSharedListActions'

import type { SharedListDetail } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { parseServerDate } from '@/lib/server-time'

const props = defineProps<{
  /** The list to show; none closes the dialog. */
  listId: string | null
}>()

const emit = defineEmits<{
  close: []
  /** Show the list in the preview tab. */
  preview: [listId: string]
}>()

const { t, locale } = useI18n()
const router = useRouter()
const store = useSharedListsStore()
const { confirm, confirmDestructive } = useDialog()
const { busyId, copiedId, copyLink, run } = useSharedListActions()
const { daysText } = useSharedListText()

/** Kept while the dialog closes, so its content does not blank out mid-animation. */
const current = ref<SharedListDetail | null>(null)

const open = computed(() => props.listId !== null)

watch(
  () => props.listId,
  async (id) => {
    if (!id) {
      store.closeDetail()
      return
    }
    if (current.value?.id !== id) current.value = null
    try {
      await store.fetchDetail(id)
    } catch (error) {
      // A list closed or swapped for another meanwhile: not this dialog's failure.
      if (props.listId !== id) return
      toastApiError(error)
      emit('close')
    }
  },
  { immediate: true },
)

watch(
  () => store.detail,
  (detail) => {
    if (detail && detail.id === props.listId) current.value = detail
  },
)

const meta = computed(() => {
  const list = current.value
  if (!list) return ''
  const created = parseServerDate(list.created_at)?.toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  const by = list.created_by_name
    ? t('sharedLists.detail.createdBy', { name: list.created_by_name, date: created })
    : t('sharedLists.detail.created', { date: created })
  return `${list.share_note || t('sharedLists.rows.noShareNote')} · ${by}`
})

const figures = computed(() => {
  const list = current.value
  if (!list) return []
  return [
    { key: 'signups', label: t('sharedLists.detail.figures.signups'), value: list.signup_count },
    { key: 'guests', label: t('sharedLists.detail.figures.guests'), value: list.guest_count },
    { key: 'free', label: t('sharedLists.detail.figures.free'), value: list.free },
    {
      key: 'views',
      label: t('sharedLists.detail.figures.views'),
      value: t('sharedLists.detail.figures.viewCount', { count: list.view_count }),
    },
  ]
})

const footer = useTemplateRef<InstanceType<typeof SharedListDetailFooter>>('footer')

const ended = computed(() => current.value?.effective_status === 'ended')
const locked = computed(() => current.value?.access === 'manager' && store.reshareLocked)

async function act(action: ListAction) {
  const list = current.value
  if (!list) return
  if (action === 'rotate') {
    const ok = await confirm({
      title: t('sharedLists.confirm.rotate.title'),
      text: t('sharedLists.confirm.rotate.text'),
      confirmText: t('sharedLists.confirm.rotate.confirm'),
    })
    if (!ok) return
  } else if (action === 'end') {
    const ok = await confirmDestructive({
      title: t('sharedLists.confirm.end.title'),
      text: t('sharedLists.confirm.end.text'),
      confirmText: t('sharedLists.actions.end'),
      // Ended before the question has closed: its button is gone by then.
      focusInstead: () => footer.value?.focusMain(),
    })
    if (!ok) return
  }
  await run(list, action)
}

function edit() {
  const list = current.value
  if (!list) return
  void router.push({
    name: 'shared-list-edit',
    params: { eventId: list.event.id, listId: list.id },
  })
}

/** The list's notice to hang up, with its QR code and the shifts it offers. */
function printNotice() {
  const list = current.value
  if (list) void router.push({ name: 'print-list', params: { listId: list.id } })
}

function shareAgain() {
  const list = current.value
  if (!list) return
  void router.push({
    name: 'shared-list-create',
    params: { eventId: list.event.id },
    query: { from: list.id },
  })
}
</script>

<template>
  <ResponsiveDialog :open="open" @update:open="(value) => !value && emit('close')">
    <ResponsiveDialogContent dialog-class="sm:max-w-2xl" data-testid="shared-list-detail">
      <ResponsiveDialogHeader>
        <div v-if="current" class="flex flex-wrap items-center gap-2">
          <SharedListStatusBadge :status="current.effective_status" />
        </div>
        <ResponsiveDialogTitle
          class="text-xl leading-tight font-bold"
          data-testid="shared-list-detail-title"
        >
          {{ current?.title ?? t('common.states.loading') }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="text-[13px]">
          {{ meta }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <!-- Rows as tall as their content: the body is a scroll box of fixed height,
           and an `auto` row would let the figures (`overflow-hidden`, so no
           minimum height) shrink to their border once the content overflows. -->
      <ResponsiveDialogBody class="grid auto-rows-max content-start gap-6 pb-5">
        <p v-if="!current" class="py-6 text-center text-sm text-muted-foreground">
          {{ t('common.states.loading') }}
        </p>
        <template v-else>
          <p
            v-if="current.access === 'viewer'"
            class="flex items-start gap-2 rounded-xl bg-muted px-3 py-2.5 text-[13px]"
            data-testid="shared-list-detail-readonly"
          >
            <Lock class="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            {{ t('sharedLists.detail.lockNote') }}
          </p>
          <p
            v-else-if="locked"
            class="flex items-start gap-2 rounded-xl bg-muted px-3 py-2.5 text-[13px]"
            data-testid="shared-list-detail-locked"
          >
            <Lock class="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            {{ t('sharedLists.page.managersOff') }}
          </p>

          <SharedListLinkBox
            v-if="!ended"
            :key="current.id"
            :list="current"
            :copied="copiedId === current.id"
            @copy="copyLink(current)"
            @preview="emit('preview', current.id)"
            @print="printNotice"
          />

          <dl
            class="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-4"
            data-testid="shared-list-figures"
          >
            <div
              v-for="figure in figures"
              :key="figure.key"
              class="flex flex-col-reverse bg-card px-3 py-2.5"
            >
              <dt class="text-xs text-muted-foreground">{{ figure.label }}</dt>
              <dd
                class="text-lg leading-tight font-bold tabular-nums"
                :data-testid="`shared-list-figure-${figure.key}`"
              >
                {{ figure.value }}
              </dd>
            </div>
          </dl>

          <section class="grid gap-3" aria-labelledby="shared-list-detail-tasks">
            <h3 id="shared-list-detail-tasks" class="text-[15px] font-bold">
              {{ t('sharedLists.detail.tasksTitle') }}
            </h3>
            <ul class="grid gap-3">
              <li
                v-for="task in current.detail_tasks"
                :key="task.id"
                class="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_11rem] sm:items-center"
                data-testid="shared-list-detail-task"
              >
                <p class="text-[13.5px]">
                  <span class="font-semibold">{{ task.name }}</span>
                  <span class="text-muted-foreground">
                    ·
                    {{
                      t('sharedLists.tasks.shifts', { count: task.shift_count }, task.shift_count)
                    }}
                    <template v-if="task.only_days">
                      · {{ t('sharedLists.rows.onlyDays', { days: daysText(task.only_days) }) }}
                    </template>
                  </span>
                </p>
                <FillBar v-if="task.offered" :free="task.free" :cap="task.capacity" />
                <p
                  v-else-if="task.not_offered_reason"
                  class="flex items-start gap-1.5 text-[13px] text-warning"
                  data-testid="shared-list-detail-task-not-offered"
                >
                  <TriangleAlert class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  {{ t(`sharedLists.detail.notOffered.${task.not_offered_reason}`) }}
                </p>
              </li>
            </ul>
            <p class="text-xs text-muted-foreground">{{ t('sharedLists.detail.laterShifts') }}</p>
          </section>

          <SharedListSignups :key="current.id" :list-id="current.id" />

          <section class="grid gap-3" aria-labelledby="shared-list-detail-settings">
            <h3 id="shared-list-detail-settings" class="text-[15px] font-bold">
              {{ t('sharedLists.detail.settingsTitle') }}
            </h3>
            <SharedListSettingsSummary :list="current" />
          </section>
        </template>
      </ResponsiveDialogBody>

      <SharedListDetailFooter
        v-if="current && canManageList(current)"
        ref="footer"
        :list="current"
        :busy="busyId === current.id"
        :locked="locked"
        @act="act"
        @edit="edit"
        @share-again="shareAgain"
      />
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
