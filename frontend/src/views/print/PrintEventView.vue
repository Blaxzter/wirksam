<script setup lang="ts">
/**
 * The whole event on paper. `?mode=overview` (the default) puts its tasks on
 * one page with a QR code to the event in the app. `?mode=all` prints each
 * task's sheet in turn.
 *
 * For someone who can share lists, the sheets of every task that can be
 * offered carry one shared list's QR code (`?list=<id>`) and its shifts: the
 * list that holds those tasks, or one created after asking. The other tasks
 * print without a QR code, as do all of them for anyone else.
 */
import { computed, onMounted, ref, shallowRef, useTemplateRef } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useSharedListsStore } from '@/stores/sharedLists'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { usePrintSheet } from '@/composables/usePrintSheet'
import { useSharedListPrint } from '@/composables/useSharedListPrint'

import PrintEventOverview from '@/components/print/PrintEventOverview.vue'
import PrintListStatus from '@/components/print/PrintListStatus.vue'
import PrintSheet from '@/components/print/PrintSheet.vue'
import PrintSheetOptions from '@/components/print/PrintSheetOptions.vue'
import PrintToolbar from '@/components/print/PrintToolbar.vue'
import SharedListPrintDialog from '@/components/shared-lists/SharedListPrintDialog.vue'

import type {
  EventRead,
  SharedListDetail,
  ShiftBatchRead,
  ShiftRead,
  TaskListResponse,
  TaskRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { formatDate } from '@/lib/format'
import { type SheetShift, fromShift } from '@/lib/print-sheet'
import { eventListTitle } from '@/lib/shared-list-print'
import { lockedForManager, sharedListUrl } from '@/lib/shared-lists'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { get } = useAuthenticatedClient()
const store = useSharedListsStore()
const notice = useSharedListPrint()
const sheet = usePrintSheet()

const eventId = computed(() => String(route.params.eventId))
const mode = computed(() => (route.query.mode === 'all' ? 'all' : 'overview'))

const event = ref<EventRead | null>(null)
const tasks = ref<TaskRead[]>([])
const shiftsByTask = shallowRef<ReadonlyMap<string, ShiftRead[]>>(new Map())
const batchesByTask = shallowRef<ReadonlyMap<string, ShiftBatchRead[]>>(new Map())
const loading = ref(true)

/** The list behind the QR codes, and the shifts it offers per task. */
const list = ref<SharedListDetail | null>(null)
const offeredByTask = shallowRef<ReadonlyMap<string, SheetShift[]>>(new Map())

const overview = useTemplateRef<InstanceType<typeof PrintEventOverview>>('overview')
const sheetEls = useTemplateRef<InstanceType<typeof PrintSheet>[]>('sheetEls')
const toolbar = useTemplateRef<InstanceType<typeof PrintToolbar>>('toolbar')

const listLive = computed(() => list.value?.effective_status === 'live')
const locked = computed(() => !!list.value && lockedForManager(list.value, event.value))

/** One sheet per task: the list's shifts and QR code where it offers some of the task's. */
const sheets = computed(() =>
  tasks.value.map((task) => {
    const offered = offeredByTask.value.get(task.id)
    return {
      task,
      shifts: offered ?? (shiftsByTask.value.get(task.id) ?? []).map(fromShift),
      qr:
        offered && list.value
          ? { url: sharedListUrl(list.value.code), caption: t('print.listQrCaption') }
          : null,
    }
  }),
)

const listed = computed(() => sheets.value.some((item) => item.qr))

const groups = () => sheets.value.map((item) => item.shifts)
const taskIds = () => tasks.value.map((task) => task.id)

/** Each task's batches; a task whose batches fail prints its shifts without their headings. */
async function fetchBatches(): Promise<Map<string, ShiftBatchRead[]>> {
  const batches = new Map<string, ShiftBatchRead[]>()
  await Promise.all(
    tasks.value.map((task) =>
      get<{ data: ShiftBatchRead[] }>({ url: `/tasks/${task.id}/batches` }).then(
        (res) => batches.set(task.id, res.data),
        () => batches.set(task.id, []),
      ),
    ),
  )
  return batches
}

async function loadShifts() {
  const [shifts, batches] = await Promise.all([sheet.fetchShifts(taskIds()), fetchBatches()])
  shiftsByTask.value = shifts
  batchesByTask.value = batches
}

/** The list in `?list=`: its state and the shifts it offers of each task. */
async function loadList(listId: string) {
  try {
    const known = new Map([...shiftsByTask.value.values()].flat().map((s) => [s.id, s]))
    const { list: detail, offered } = await sheet.fetchListSheet(listId, known)
    list.value = detail
    offeredByTask.value = offered
  } catch (error) {
    toastApiError(error)
    list.value = null
    offeredByTask.value = new Map()
  }
}

async function showList(listId: string) {
  await router.replace({ query: { ...route.query, list: listId } })
  await loadList(listId)
  sheet.reset(groups(), taskIds())
}

/** Look for the list to print with, or ask whether to create one. */
async function chooseList(ev: EventRead) {
  try {
    const outcome = await notice.startEvent(
      ev,
      tasks.value,
      (taskId) => shiftsByTask.value.get(taskId) ?? [],
      eventListTitle(ev.name, t),
    )
    if (outcome.kind === 'list') await showList(outcome.listId)
  } catch (error) {
    toastApiError(error)
  }
}

async function createList() {
  const listId = await notice.createList()
  if (listId) await showList(listId)
}

function customize() {
  const to = notice.wizardRoute()
  if (to) void router.push(to)
}

/** After a fix in the toolbar: the list as it is now, the viewer's choices kept, focus on printing. */
async function refreshList() {
  if (!list.value) return
  await loadList(list.value.id)
  sheet.refresh(groups(), taskIds())
  void toolbar.value?.focusPrint()
}

/** The dialog opened with the page, so no button takes focus back: printing does. */
function focusPrint() {
  void toolbar.value?.focusPrint()
}

function print() {
  if (mode.value === 'all') void sheet.print(sheetEls.value ?? [])
  else if (overview.value) void sheet.print([overview.value])
}

onMounted(async () => {
  try {
    const [eventRes, tasksRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${eventId.value}` }),
      get<{ data: TaskListResponse }>({
        url: '/tasks/',
        query: { limit: 200, event_id: eventId.value },
      }),
    ])
    event.value = eventRes.data
    tasks.value = [...tasksRes.data.items].sort((a, b) => a.start_date.localeCompare(b.start_date))
    if (mode.value !== 'all') return
    // The fixes in the toolbar go through the lists store, which reloads by event.
    store.setEvent(eventRes.data.id)
    await loadShifts()
    const listId = typeof route.query.list === 'string' ? route.query.list : null
    if (listId) await loadList(listId)
    sheet.reset(groups(), taskIds())
    if (!listId) await chooseList(eventRes.data)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="print-page mx-auto max-w-5xl w-full space-y-4 p-4 print:p-0">
    <PrintToolbar
      ref="toolbar"
      data-testid="print-toolbar"
      :disabled="loading || sheet.bookingsLoading.value || (!!list && !listLive)"
      @print="print"
    >
      <template v-if="mode === 'all'">
        <PrintListStatus v-if="list" :list="list" :locked="locked" @changed="refreshList" />
        <PrintSheetOptions
          v-model:show-title="sheet.showTitle.value"
          v-model:show-location="sheet.showLocation.value"
          v-model:repeat-header="sheet.repeatHeader.value"
          v-model:show-map="sheet.showMap.value"
          v-model:paper-lines="sheet.paperLines.value"
          v-model:selected-dates="sheet.selectedDates.value"
          :include-names="sheet.includeNames.value"
          :dates="sheet.dates.value"
          :has-map="false"
          :listed="listed"
          :bookings-loading="sheet.bookingsLoading.value"
          @update:include-names="sheet.setIncludeNames"
        />
      </template>
    </PrintToolbar>

    <p v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>

    <div v-else-if="event" data-testid="print-content">
      <PrintEventOverview v-if="mode === 'overview'" ref="overview" :event="event" :tasks="tasks" />

      <template v-else>
        <PrintSheet
          v-for="(item, index) in sheets"
          :key="item.task.id"
          ref="sheetEls"
          :page-break="index > 0"
          :heading="item.task.name"
          :kicker="event.name"
          :text="item.task.description"
          :meta="{
            days: `${formatDate(item.task.start_date)} – ${formatDate(item.task.end_date)}`,
            location: item.task.location,
            category: item.task.category,
          }"
          :qr="item.qr"
          :sections="[
            {
              key: item.task.id,
              heading: null,
              shifts: sheet.visible(item.shifts),
              batches: batchesByTask.get(item.task.id) ?? [],
              canSeeContacts: !!item.task.can_manage,
            },
          ]"
          :options="sheet.options.value"
          :bookings="sheet.bookings.value"
        />
      </template>
    </div>

    <SharedListPrintDialog
      :dialog="notice.dialog.value"
      :busy="notice.creating.value"
      :return-focus="focusPrint"
      @create="createList"
      @customize="customize"
      @plain="notice.close"
      @close="notice.close"
    />
  </div>
</template>
