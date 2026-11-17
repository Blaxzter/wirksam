<script setup lang="ts">
/**
 * One list on its own page (`/app/shared-lists/:eventId/:listId`): its link
 * and QR code, the figures, who signed up through it, what it offers and its
 * settings, with what can be done with it under the heading.
 *
 * From `xl` up, the sign-ups and the tasks take the main column and the link
 * and settings stay in view beside them; below that it is one column, the link
 * first, since that is what is wanted most on a phone. Rotating and ending ask
 * first. A list the viewer may only read says why and offers no actions.
 *
 * The overview's old address for the details, `?list=<id>`, comes here.
 */
import { computed, onBeforeUnmount, useTemplateRef, watch } from 'vue'

import { ArrowLeft, Lock, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { useBreadcrumbStore } from '@/stores/breadcrumb'
import { type ListAction, useSharedListsStore } from '@/stores/sharedLists'

import { useDialog } from '@/composables/useDialog'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import FillBar from '@/components/data-table/FillBar.vue'
import SharedListDetailActions from '@/components/shared-lists/SharedListDetailActions.vue'
import SharedListLinkBox from '@/components/shared-lists/SharedListLinkBox.vue'
import SharedListSettingsSummary from '@/components/shared-lists/SharedListSettingsSummary.vue'
import SharedListSignups from '@/components/shared-lists/SharedListSignups.vue'
import SharedListStatusBadge from '@/components/shared-lists/SharedListStatusBadge.vue'
import { PREVIEW_KEY, TAB_KEY } from '@/components/shared-lists/pageQuery'
import { useSharedListText } from '@/components/shared-lists/sharedListText'
import { canManageList, useSharedListActions } from '@/components/shared-lists/useSharedListActions'

import { toastApiError } from '@/lib/api-errors'
import { parseServerDate } from '@/lib/server-time'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useSharedListsStore()
const breadcrumbStore = useBreadcrumbStore()
const { confirm, confirmDestructive } = useDialog()
const { busyId, copiedId, copyLink, run } = useSharedListActions()
const { daysText } = useSharedListText()

const eventId = computed(() => String(route.params.eventId ?? ''))
const listId = computed(() => String(route.params.listId ?? ''))
const listsPage = computed(() => ({ name: 'shared-lists', params: { eventId: eventId.value } }))

// The overview says whether sharing is off for people in charge (`reshareLocked`).
watch(
  eventId,
  (id) => {
    store.setEvent(id)
    store.fetchOverview().catch(() => {})
  },
  { immediate: true },
)

watch(
  listId,
  async (id) => {
    try {
      await store.fetchDetail(id)
    } catch (error) {
      // Another list has taken over meanwhile: not this one's failure.
      if (listId.value !== id) return
      toastApiError(error)
      await router.replace(listsPage.value)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => store.closeDetail())

/** The list this page names, once loaded; never the one before it. */
const list = computed(() => (store.detail?.id === listId.value ? store.detail : null))

watch(
  () => list.value?.title,
  (title) => {
    if (!title) return
    breadcrumbStore.setBreadcrumbs([
      {
        title: 'Shared lists',
        titleKey: 'navigation.sidebar.items.sharedLists.label',
        to: listsPage.value,
      },
      { title },
    ])
  },
  { immediate: true },
)

const meta = computed(() => {
  const current = list.value
  if (!current) return ''
  const created = parseServerDate(current.created_at)?.toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  const by = current.created_by_name
    ? t('sharedLists.detail.createdBy', { name: current.created_by_name, date: created })
    : t('sharedLists.detail.created', { date: created })
  return `${current.share_note || t('sharedLists.rows.noShareNote')} · ${by}`
})

const figures = computed(() => {
  const current = list.value
  if (!current) return []
  return [
    { key: 'signups', label: t('sharedLists.detail.figures.signups'), value: current.signup_count },
    { key: 'guests', label: t('sharedLists.detail.figures.guests'), value: current.guest_count },
    { key: 'free', label: t('sharedLists.detail.figures.free'), value: current.free },
    {
      key: 'views',
      label: t('sharedLists.detail.figures.views'),
      value: t('sharedLists.detail.figures.viewCount', { count: current.view_count }),
    },
  ]
})

const actions = useTemplateRef<InstanceType<typeof SharedListDetailActions>>('actions')

const ended = computed(() => list.value?.effective_status === 'ended')
const locked = computed(() => list.value?.access === 'manager' && store.reshareLocked)

async function act(action: ListAction) {
  const current = list.value
  if (!current) return
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
      focusInstead: () => actions.value?.focusMain(),
    })
    if (!ok) return
  }
  await run(current, action)
}

function edit() {
  const current = list.value
  if (!current) return
  void router.push({
    name: 'shared-list-edit',
    params: { eventId: current.event.id, listId: current.id },
  })
}

/** The list's notice to hang up, with its QR code and the shifts it offers. */
function printNotice() {
  const current = list.value
  if (current) void router.push({ name: 'print-list', params: { listId: current.id } })
}

/** The list's page as a guest sees it, in the overview's preview tab. */
function preview() {
  const current = list.value
  if (!current) return
  void router.push({
    name: 'shared-lists',
    params: { eventId: current.event.id },
    query: { [TAB_KEY]: 'preview', [PREVIEW_KEY]: current.id },
  })
}

function shareAgain() {
  const current = list.value
  if (!current) return
  void router.push({
    name: 'shared-list-create',
    params: { eventId: current.event.id },
    query: { from: current.id },
  })
}
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6" data-testid="shared-list-detail">
    <div class="space-y-3">
      <!-- Below xl the header's own crumb leads back already. -->
      <Button as-child variant="ghost" size="sm" class="-ml-2 max-xl:hidden" data-testid="btn-back">
        <RouterLink :to="listsPage">
          <ArrowLeft class="mr-1.5 h-4 w-4" aria-hidden="true" />
          {{ t('sharedLists.detail.backToLists') }}
        </RouterLink>
      </Button>

      <div v-if="!list" class="space-y-3" aria-busy="true">
        <span class="sr-only">{{ t('common.states.loading') }}</span>
        <Skeleton class="h-6 w-20 rounded-full" />
        <Skeleton class="h-9 w-full max-w-md" />
        <Skeleton class="h-4 w-full max-w-sm" />
      </div>

      <div v-else class="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div class="min-w-0 space-y-1.5">
          <SharedListStatusBadge :status="list.effective_status" />
          <h1
            class="text-2xl font-bold break-words sm:text-3xl"
            data-testid="shared-list-detail-title"
          >
            {{ list.title }}
          </h1>
          <p class="text-sm text-muted-foreground">{{ meta }}</p>
        </div>
        <SharedListDetailActions
          v-if="canManageList(list)"
          ref="actions"
          class="max-md:w-full"
          :list="list"
          :busy="busyId === list.id"
          :locked="locked"
          @act="act"
          @edit="edit"
          @share-again="shareAgain"
        />
      </div>
    </div>

    <div v-if="!list" class="grid gap-4" aria-hidden="true">
      <Skeleton class="h-20 w-full rounded-xl" />
      <Skeleton class="h-48 w-full rounded-xl" />
    </div>

    <template v-else>
      <p
        v-if="list.access === 'viewer'"
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

      <div class="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start">
        <div class="grid min-w-0 gap-8">
          <dl
            class="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-4"
            data-testid="shared-list-figures"
          >
            <div
              v-for="figure in figures"
              :key="figure.key"
              class="flex flex-col-reverse bg-card px-4 py-3"
            >
              <dt class="text-xs text-muted-foreground">{{ figure.label }}</dt>
              <dd
                class="text-xl leading-tight font-bold tabular-nums"
                :data-testid="`shared-list-figure-${figure.key}`"
              >
                {{ figure.value }}
              </dd>
            </div>
          </dl>

          <SharedListSignups :key="list.id" :list-id="list.id" />

          <section class="grid gap-3" aria-labelledby="shared-list-detail-tasks">
            <h2 id="shared-list-detail-tasks" class="text-lg font-bold">
              {{ t('sharedLists.detail.tasksTitle') }}
            </h2>
            <ul class="grid divide-y rounded-xl border bg-card">
              <li
                v-for="task in list.detail_tasks"
                :key="task.id"
                class="grid gap-1.5 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_12rem] sm:items-center"
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
        </div>

        <!-- Beside the main column from xl, in view while it scrolls. Below
             that its sections join the one column: the link first, which a
             phone wants most, the settings last. -->
        <div
          class="contents xl:sticky xl:top-[calc(var(--app-header-height,3.5rem)+1rem)] xl:grid xl:min-w-0 xl:gap-4"
        >
          <section
            v-if="!ended"
            class="order-first grid gap-3 rounded-xl border bg-card p-4 xl:order-none"
            aria-labelledby="shared-list-detail-link"
          >
            <h2 id="shared-list-detail-link" class="text-[15px] font-bold">
              {{ t('sharedLists.detail.linkTitle') }}
            </h2>
            <SharedListLinkBox
              :key="list.id"
              :list="list"
              :copied="copiedId === list.id"
              @copy="copyLink(list)"
              @preview="preview"
              @print="printNotice"
            />
          </section>

          <section
            class="order-last grid gap-3 rounded-xl border bg-card p-4 xl:order-none"
            aria-labelledby="shared-list-detail-settings"
          >
            <h2 id="shared-list-detail-settings" class="text-[15px] font-bold">
              {{ t('sharedLists.detail.settingsTitle') }}
            </h2>
            <SharedListSettingsSummary :list="list" />
          </section>
        </div>
      </div>
    </template>
  </div>
</template>
