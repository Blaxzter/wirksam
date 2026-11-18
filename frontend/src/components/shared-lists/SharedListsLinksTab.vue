<script setup lang="ts">
/**
 * The "Links" tab: the figures, what has no open list, and the event's lists
 * as a table (cards on a phone) with filter chips, a search, sorting and
 * pages, all on the server and kept in the address. Ticked rows can be
 * paused, resumed or ended together; event admins also get the emergency
 * stop and the switch for people in charge.
 */
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'

import { CircleStop, Pause, Play } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import {
  type BulkAction,
  type ListAction,
  type ListFilter,
  type ListParams,
  type ListSort,
  useSharedListsStore,
} from '@/stores/sharedLists'

import { useRowSelection } from '@/composables/useRowSelection'
import { useTableQuery } from '@/composables/useTableQuery'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import FilterChips, { type FilterChip } from '@/components/data-table/FilterChips.vue'
import ListPagination from '@/components/data-table/ListPagination.vue'
import SearchField from '@/components/data-table/SearchField.vue'
import SelectionBar, { type SelectionAction } from '@/components/data-table/SelectionBar.vue'
import SharedListManagersSwitch from '@/components/shared-lists/SharedListManagersSwitch.vue'
import SharedListSummaryBar from '@/components/shared-lists/SharedListSummaryBar.vue'
import SharedListsCardList from '@/components/shared-lists/SharedListsCardList.vue'
import SharedListsPauseAllConfirm from '@/components/shared-lists/SharedListsPauseAllConfirm.vue'
import SharedListsTable from '@/components/shared-lists/SharedListsTable.vue'
import SortSelect from '@/components/shared-lists/SortSelect.vue'
import UnsharedTasksNotice from '@/components/shared-lists/UnsharedTasksNotice.vue'
import {
  LIST_SORT_DIRS,
  WIDE_TABLE_QUERY,
  isListSelectable,
  useSharedListActions,
} from '@/components/shared-lists/useSharedListActions'

import type { SharedListBulkResult, SharedListRow } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { firstCheckbox } from '@/lib/focus'

const emit = defineEmits<{
  /** Open a list's details. */
  open: [listId: string]
  /** Go to the tasks with free places no open list offers. */
  showTodoTasks: []
}>()

const LIST_SORTS = ['status', 'title', 'free', 'signups', 'closes', 'created_at'] as const
const LIST_FILTERS = ['active', 'todo', 'live', 'paused', 'ended'] as const

const { t } = useI18n()
const store = useSharedListsStore()
const wide = useMediaQuery(WIDE_TABLE_QUERY)

const table = useTableQuery<ListSort, ListFilter>({
  sortKeys: LIST_SORTS,
  defaultSort: 'status',
  sortDirs: LIST_SORT_DIRS,
  filters: LIST_FILTERS,
  defaultFilter: 'active',
})
const { page, q, sort, dir, setSort } = table
const filter = computed<ListFilter>({
  get: () => table.filter.value ?? 'active',
  set: (value) => (table.filter.value = value),
})

const rows = computed<SharedListRow[]>(() => store.lists?.items ?? [])
const selection = useRowSelection({
  rows,
  rowId: (row) => row.id,
  isSelectable: isListSelectable,
  clearOn: table.key,
})
const { busyId, copiedId, copyLink, run } = useSharedListActions()

const tab = useTemplateRef<HTMLElement>('tab')
const rowsView = useTemplateRef<{ $el: HTMLElement }>('rowsView')

/** The table's own checkbox, or the chip on show once no row is left to tick. */
const focusRows = () =>
  firstCheckbox(rowsView.value?.$el) ??
  tab.value?.querySelector<HTMLElement>('[aria-pressed="true"]')

const zone = computed(() => store.overview?.event_timezone ?? '')

async function load(params: ListParams) {
  try {
    await store.fetchLists(params)
  } catch (error) {
    // A newer search or page has taken over; only its own failure is news.
    if (params === table.params.value) toastApiError(error)
  }
}
watch(table.params, load, { immediate: true })

// Ending the last lists of the last page leaves it empty: step back.
watch(
  () => store.lists?.total,
  (total) => {
    if (total !== undefined) table.clampTo(total)
  },
)

const chips = computed<FilterChip<ListFilter>[]>(() =>
  LIST_FILTERS.map((value) => ({
    value,
    label: t(`sharedLists.filters.${value}`),
    count: store.lists?.counts[value],
    variant: value === 'todo' ? 'warning' : 'default',
  })),
)

const sortOptions = computed(() =>
  LIST_SORTS.map((value) => ({ value, label: t(`sharedLists.sort.${value}`) })),
)

const emptyText = computed(() => {
  const current = store.lists
  if (!current || current.items.length > 0) return null
  if (q.value) return t('sharedLists.empty.search', { q: q.value })
  if (filter.value === 'todo') return t('sharedLists.empty.todo')
  if (current.counts.active + current.counts.ended === 0) return t('sharedLists.empty.none')
  return t('sharedLists.empty.filter')
})

/** "2 ended lists are hidden · Show": only under the default chip. */
const endedLine = computed(() => {
  const count = store.lists?.ended_matching ?? 0
  if (filter.value !== 'active' || count === 0) return null
  const key = q.value ? 'sharedLists.empty.endedMatching' : 'sharedLists.empty.endedHidden'
  return t(key, { count }, count)
})

/**
 * A change to one list can take away the control it was made from: the fix
 * goes with its issue, and a row that leaves the chip or moves with the sort
 * drops focus as well. Focus then goes back to that control if it is still on
 * the page, else to the list's title, else to the table.
 */
async function act(row: SharedListRow, action: ListAction) {
  const had = document.activeElement
  await run(row, action)
  await nextTick()
  if (document.activeElement !== document.body) return
  const title = rowsView.value?.$el.querySelector<HTMLElement>(
    `[data-list-id="${row.id}"] [data-list-title]`,
  )
  const back = had instanceof HTMLElement && had.isConnected ? had : (title ?? focusRows())
  back?.focus()
}

// --- The ticked lists ---

const confirmingEnd = ref(false)
const bulkRunning = ref(false)

watch(selection.count, (count) => {
  if (count === 0) confirmingEnd.value = false
})

const bulkActions = computed<SelectionAction[]>(() => {
  const picked = selection.selectedRows.value
  const any = (test: (row: SharedListRow) => boolean) => picked.some(test)
  return [
    {
      id: 'pause',
      label: t('sharedLists.actions.pause'),
      icon: Pause,
      disabled: bulkRunning.value || !any((row) => row.effective_status === 'live'),
    },
    {
      id: 'resume',
      label: t('sharedLists.actions.resume'),
      icon: Play,
      disabled:
        bulkRunning.value ||
        store.reshareLocked ||
        !any((row) => row.effective_status === 'paused' || row.effective_status === 'expired'),
    },
    {
      id: 'end',
      label: t('sharedLists.actions.end'),
      icon: CircleStop,
      destructive: true,
      disabled: bulkRunning.value,
    },
  ]
})

function report(action: BulkAction, result: SharedListBulkResult) {
  const changed = result.changed.length
  const skipped = result.skipped.length
  if (changed > 0) {
    toast.success(t(`sharedLists.toasts.bulk.${action}`, { count: changed }, changed))
  }
  if (skipped > 0) {
    toast.warning(t('sharedLists.toasts.bulkSkipped', { count: skipped }, skipped))
  }
  if (changed === 0 && skipped === 0) toast.info(t('sharedLists.toasts.nothingChanged'))
}

async function runBulk(action: BulkAction) {
  if (bulkRunning.value) return
  bulkRunning.value = true
  try {
    report(action, await store.bulk(action, selection.selectedIds.value))
    selection.clear()
  } catch (error) {
    toastApiError(error)
  } finally {
    bulkRunning.value = false
    confirmingEnd.value = false
  }
}

function onBulkAction(id: string) {
  if (id === 'end') confirmingEnd.value = true
  else if (id === 'pause' || id === 'resume') void runBulk(id)
}

// --- Pausing everything ---

const pauseAllOpen = ref(false)
const pauseAllButton = useTemplateRef<{ $el: HTMLElement }>('pauseAllButton')

async function closePauseAll() {
  pauseAllOpen.value = false
  await nextTick()
  pauseAllButton.value?.$el.focus()
}
</script>

<template>
  <section ref="tab" class="grid grid-cols-1 gap-5" data-testid="shared-lists-links">
    <!-- One column as wide as the page: a column sized to its content would
         grow to the whole row of filter chips, which scrolls sideways instead. -->
    <SharedListSummaryBar v-if="store.overview" :summary="store.overview.summary" />
    <UnsharedTasksNotice
      v-if="store.overview"
      :notice="store.overview.unshared"
      @show="emit('showTodoTasks')"
    />

    <div class="grid grid-cols-1 gap-3">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterChips v-model="filter" :chips="chips" :label="t('sharedLists.filters.label')" />
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div class="sm:w-64">
            <SearchField
              v-model="q"
              :label="t('sharedLists.search.lists')"
              :placeholder="t('sharedLists.search.listsPlaceholder')"
            />
          </div>
          <Button
            v-if="store.overview?.can_pause_all"
            ref="pauseAllButton"
            variant="outline"
            class="max-sm:h-11"
            :aria-expanded="pauseAllOpen"
            data-testid="shared-lists-pause-all"
            @click="pauseAllOpen = !pauseAllOpen"
          >
            <Pause aria-hidden="true" />
            {{ t('sharedLists.pauseAll.button') }}
          </Button>
        </div>
      </div>
      <SortSelect
        v-if="!wide"
        :options="sortOptions"
        :sort="sort"
        :dir="dir"
        @sort="(key, direction) => setSort(key, direction)"
      />
    </div>

    <SharedListsPauseAllConfirm
      v-if="pauseAllOpen && store.overview"
      :count="store.overview.summary.live_lists"
      @close="closePauseAll"
    />

    <div v-if="!store.lists" class="grid gap-2.5" aria-busy="true">
      <Skeleton v-for="i in 3" :key="i" class="h-24 w-full rounded-xl" />
    </div>

    <template v-else>
      <p
        v-if="emptyText"
        class="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground"
        data-testid="shared-lists-empty"
      >
        {{ emptyText }}
      </p>
      <template v-else>
        <SharedListsTable
          v-if="wide"
          ref="rowsView"
          :rows="rows"
          :zone="zone"
          :selection="selection"
          :sort="sort"
          :dir="dir"
          :busy-id="busyId"
          :copied-id="copiedId"
          :locked="store.reshareLocked"
          :loading="store.listsLoading"
          @sort="setSort"
          @open="(row) => emit('open', row.id)"
          @copy="copyLink"
          @act="act"
        />
        <SharedListsCardList
          v-else
          ref="rowsView"
          :rows="rows"
          :zone="zone"
          :selection="selection"
          :busy-id="busyId"
          :copied-id="copiedId"
          :locked="store.reshareLocked"
          :loading="store.listsLoading"
          @open="(row) => emit('open', row.id)"
          @copy="copyLink"
          @act="act"
        />
      </template>

      <SelectionBar
        :count="selection.count.value"
        :actions="bulkActions"
        :confirming="confirmingEnd"
        :label="t('sharedLists.bulk.region')"
        :focus-on-leave="focusRows"
        @action="onBulkAction"
        @clear="selection.clear()"
      >
        <template #confirm>
          <p class="min-w-0 flex-1 basis-56 text-sm">
            <strong>
              {{
                t(
                  'sharedLists.bulk.endTitle',
                  { count: selection.count.value },
                  selection.count.value,
                )
              }}
            </strong>
            {{ t('sharedLists.bulk.endText', selection.count.value) }}
          </p>
          <Button
            variant="destructive"
            size="sm"
            class="aria-disabled:opacity-50"
            :aria-disabled="bulkRunning || undefined"
            data-testid="shared-lists-bulk-end-confirm"
            @click="runBulk('end')"
          >
            {{ t('sharedLists.bulk.confirmEnd') }}
          </Button>
          <Button variant="ghost" size="sm" @click="confirmingEnd = false">
            {{ t('common.actions.cancel') }}
          </Button>
        </template>
      </SelectionBar>

      <ListPagination v-model:page="page" :total="store.lists.total" :page-size="table.pageSize" />

      <p
        v-if="endedLine"
        class="text-center text-[13px] text-muted-foreground"
        data-testid="shared-lists-ended-hidden"
      >
        {{ endedLine }}
        <Button
          variant="link"
          size="sm"
          class="h-auto px-1 text-[13px]"
          data-testid="shared-lists-show-ended"
          @click="filter = 'ended'"
        >
          {{ t('sharedLists.actions.show') }}
        </Button>
      </p>
    </template>

    <SharedListManagersSwitch
      v-if="store.overview"
      :enabled="store.overview.managers_share_lists"
      :is-admin="store.overview.is_admin"
    />
  </section>
</template>
