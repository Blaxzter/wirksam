<script setup lang="ts">
/**
 * The "Tasks" tab: the event's published tasks with shifts ahead (only their
 * own for a person in charge), and which lists offer their free places.
 * "To do" holds those with free places in no open list. Ticking several and
 * sharing them starts one list for all of them, so a group needs one link.
 */
import { computed, useTemplateRef, watch } from 'vue'

import { Lock, Share2 } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import {
  type TaskFilter,
  type TaskParams,
  type TaskSort,
  useSharedListsStore,
} from '@/stores/sharedLists'

import { useRowSelection } from '@/composables/useRowSelection'
import { useTableQuery } from '@/composables/useTableQuery'

import { Skeleton } from '@/components/ui/skeleton'

import FilterChips, { type FilterChip } from '@/components/data-table/FilterChips.vue'
import ListPagination from '@/components/data-table/ListPagination.vue'
import SearchField from '@/components/data-table/SearchField.vue'
import SelectionBar, { type SelectionAction } from '@/components/data-table/SelectionBar.vue'
import SharedListTasksCardList from '@/components/shared-lists/SharedListTasksCardList.vue'
import SharedListTasksTable from '@/components/shared-lists/SharedListTasksTable.vue'
import SortSelect from '@/components/shared-lists/SortSelect.vue'
import { TASKS_PREFIX } from '@/components/shared-lists/pageQuery'
import { WIDE_TABLE_QUERY } from '@/components/shared-lists/useSharedListActions'

import type { SharedListTaskRow } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { firstCheckbox } from '@/lib/focus'

const props = defineProps<{ eventId: string }>()

const emit = defineEmits<{ open: [listId: string] }>()

const TASK_SORTS = ['name', 'free', 'unlisted_free'] as const
const TASK_FILTERS = ['all', 'todo'] as const

const { t } = useI18n()
const router = useRouter()
const store = useSharedListsStore()
const wide = useMediaQuery(WIDE_TABLE_QUERY)

// Prefixed, so this tab and the links tab each keep their own view.
const table = useTableQuery<TaskSort, TaskFilter>({
  prefix: TASKS_PREFIX,
  sortKeys: TASK_SORTS,
  defaultSort: 'name',
  sortDirs: { free: 'desc', unlisted_free: 'desc' },
  filters: TASK_FILTERS,
  defaultFilter: 'all',
})
const { page, q, sort, dir, setSort } = table
const filter = computed<TaskFilter>({
  get: () => table.filter.value ?? 'all',
  set: (value) => (table.filter.value = value),
})

const rows = computed<SharedListTaskRow[]>(() => store.tasks?.items ?? [])
const selection = useRowSelection({
  rows,
  rowId: (row) => row.id,
  isSelectable: (row) => row.can_share,
  clearOn: table.key,
})

const rowsView = useTemplateRef<{ $el: HTMLElement }>('rowsView')
const focusRows = () => firstCheckbox(rowsView.value?.$el)

async function load(params: TaskParams) {
  try {
    await store.fetchTasks(params)
  } catch (error) {
    // A newer search or page has taken over; only its own failure is news.
    if (params === table.params.value) toastApiError(error)
  }
}
watch(table.params, load, { immediate: true })
watch(
  () => store.tasks?.total,
  (total) => {
    if (total !== undefined) table.clampTo(total)
  },
)

const chips = computed<FilterChip<TaskFilter>[]>(() => [
  { value: 'all', label: t('sharedLists.tasks.filters.all'), count: store.tasks?.counts.all },
  {
    value: 'todo',
    label: t('sharedLists.tasks.filters.todo'),
    count: store.tasks?.counts.todo,
    variant: 'warning',
  },
])

const sortOptions = computed(() =>
  TASK_SORTS.map((value) => ({ value, label: t(`sharedLists.tasks.sort.${value}`) })),
)

const emptyText = computed(() => {
  const current = store.tasks
  if (!current || current.items.length > 0) return null
  if (q.value) return t('sharedLists.tasks.empty.search', { q: q.value })
  if (filter.value === 'todo') return t('sharedLists.tasks.empty.todo')
  return t('sharedLists.tasks.empty.none')
})

/** A person in charge sees their own tasks only, and may not always share them. */
const scopeNote = computed(() => {
  const overview = store.overview
  if (!overview || overview.is_admin) return null
  return overview.managers_share_lists
    ? t('sharedLists.tasks.scopeNote')
    : t('sharedLists.tasks.scopeNoteOff')
})

const selectedFree = computed(() =>
  selection.selectedRows.value.reduce((sum, row) => sum + row.free, 0),
)

const shareActions = computed<SelectionAction[]>(() => [
  {
    id: 'share',
    label:
      selection.count.value === 1
        ? t('sharedLists.actions.share')
        : t('sharedLists.actions.shareAsOne'),
    icon: Share2,
  },
])

function share(taskIds: string[]) {
  void router.push({
    name: 'shared-list-create',
    params: { eventId: props.eventId },
    query: { tasks: taskIds.join(',') },
  })
}
</script>

<template>
  <section class="grid grid-cols-1 gap-5" data-testid="shared-lists-tasks">
    <!-- One column as wide as the page: a column sized to its content would
         grow to the whole row of filter chips, which scrolls sideways instead. -->
    <p class="max-w-prose text-muted-foreground">{{ t('sharedLists.tasks.intro') }}</p>
    <p
      v-if="scopeNote"
      class="flex items-start gap-2 rounded-xl bg-muted px-3 py-2.5 text-[13px]"
      data-testid="shared-list-tasks-scope"
    >
      <Lock class="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      {{ scopeNote }}
    </p>

    <div class="grid grid-cols-1 gap-3">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterChips
          v-model="filter"
          :chips="chips"
          :label="t('sharedLists.tasks.filters.label')"
        />
        <div class="sm:w-64">
          <SearchField
            v-model="q"
            :label="t('sharedLists.search.tasks')"
            :placeholder="t('sharedLists.search.tasksPlaceholder')"
          />
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

    <div v-if="!store.tasks" class="grid gap-2.5" aria-busy="true">
      <Skeleton v-for="i in 3" :key="i" class="h-20 w-full rounded-xl" />
    </div>

    <template v-else>
      <p
        v-if="emptyText"
        class="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground"
        data-testid="shared-list-tasks-empty"
      >
        {{ emptyText }}
      </p>
      <template v-else>
        <SharedListTasksTable
          v-if="wide"
          ref="rowsView"
          :rows="rows"
          :selection="selection"
          :sort="sort"
          :dir="dir"
          :loading="store.tasksLoading"
          @sort="setSort"
          @open="emit('open', $event)"
          @share="share([$event])"
        />
        <SharedListTasksCardList
          v-else
          ref="rowsView"
          :rows="rows"
          :selection="selection"
          :loading="store.tasksLoading"
          @open="emit('open', $event)"
          @share="share([$event])"
        />
      </template>

      <SelectionBar
        :count="selection.count.value"
        :actions="shareActions"
        :label="t('sharedLists.tasks.region')"
        :focus-on-leave="focusRows"
        @action="share(selection.selectedIds.value)"
        @clear="selection.clear()"
      >
        <template #message>
          <span class="font-semibold tabular-nums">
            {{
              t(
                'sharedLists.tasks.selected',
                { count: selection.count.value },
                selection.count.value,
              )
            }}
          </span>
          ·
          {{ t('sharedLists.tasks.selectedFree', { count: selectedFree }, selectedFree) }}
        </template>
      </SelectionBar>

      <ListPagination v-model:page="page" :total="store.tasks.total" :page-size="table.pageSize" />
    </template>
  </section>
</template>
