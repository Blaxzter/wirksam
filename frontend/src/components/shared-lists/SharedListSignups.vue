<script setup lang="ts">
/**
 * "Signed up through this link", in a list's details: searchable, sortable
 * and paged on the server (its state kept in the address under `signups_`),
 * a table in the dialog and rows in the phone's sheet. Sign-ups can be taken
 * off one at a time, ticked, or one and every newer one; a person in charge
 * sees those on their own tasks and how many others there are.
 *
 * Taking sign-ups off removes their rows, and with them the control focus
 * would go back to: it goes to the section's heading instead, and to the
 * table's first checkbox when the selection bar goes.
 */
import { computed, ref, useTemplateRef, watch } from 'vue'

import { UserMinus } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { type SignupSort, useSharedListsStore } from '@/stores/sharedLists'

import { useRowSelection } from '@/composables/useRowSelection'
import { useTableQuery } from '@/composables/useTableQuery'

import { useResponsiveDialog } from '@/components/ui/responsive-dialog'

import ListPagination from '@/components/data-table/ListPagination.vue'
import SearchField from '@/components/data-table/SearchField.vue'
import SelectionBar, { type SelectionAction } from '@/components/data-table/SelectionBar.vue'
import SharedListRemoveSignupsDialog, {
  type RemoveTarget,
} from '@/components/shared-lists/SharedListRemoveSignupsDialog.vue'
import SharedListSignupsCardList from '@/components/shared-lists/SharedListSignupsCardList.vue'
import SharedListSignupsTable from '@/components/shared-lists/SharedListSignupsTable.vue'
import SortSelect from '@/components/shared-lists/SortSelect.vue'
import { SIGNUPS_PREFIX } from '@/components/shared-lists/pageQuery'
import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListSignup } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { firstCheckbox } from '@/lib/focus'
import { pooledBeyond } from '@/lib/shared-lists'

const props = defineProps<{ listId: string }>()

/** Fewer than the page's tables: these sit in a dialog among other sections. */
const SIGNUPS_PAGE_SIZE = 10
const SIGNUP_SORTS = ['created_at', 'name', 'shift_start'] as const

const { t } = useI18n()
const store = useSharedListsStore()
const { isMobile } = useResponsiveDialog()
const { personName, shiftText } = useSharedListText()

const table = useTableQuery<SignupSort>({
  prefix: SIGNUPS_PREFIX,
  sortKeys: SIGNUP_SORTS,
  defaultSort: 'created_at',
  sortDirs: { created_at: 'desc' },
  pageSize: SIGNUPS_PAGE_SIZE,
})
const { page, q, sort, dir, setSort } = table

const result = computed(() => store.signups)
const rows = computed<SharedListSignup[]>(() => result.value?.items ?? [])
const selection = useRowSelection({
  rows,
  rowId: (row) => row.booking_id,
  isSelectable: (row) => row.can_remove,
  clearOn: table.key,
})

watch(
  [() => props.listId, table.params],
  async ([listId, params]) => {
    // While the dialog plays its closing animation, the address has already
    // dropped this table's keys; that is no reason to load again.
    if (store.detail?.id !== listId) return
    try {
      await store.fetchSignups(listId, params)
    } catch (error) {
      // Another list or a newer search has taken over; only its own failure is news.
      if (listId === props.listId && params === table.params.value) toastApiError(error)
    }
  },
  { immediate: true },
)
watch(
  () => store.signups?.total,
  (total) => {
    if (total !== undefined) table.clampTo(total)
  },
)

const sortOptions = computed(() =>
  SIGNUP_SORTS.map((value) => ({ value, label: t(`sharedLists.signups.sort.${value}`) })),
)

const removeOpen = ref(false)
const removeTarget = ref<RemoveTarget | null>(null)

function askRemove(target: RemoveTarget) {
  removeTarget.value = target
  removeOpen.value = true
}

function removeOne(signup: SharedListSignup) {
  askRemove({
    kind: 'bookings',
    bookingIds: [signup.booking_id],
    one: {
      name: personName(signup.name, true),
      task: signup.task_name,
      when: shiftText(signup.shift_date, signup.start_time, signup.end_time),
    },
    pooled: pooledBeyond([signup]),
  })
}

function removeSelected() {
  askRemove({
    kind: 'bookings',
    bookingIds: selection.selectedIds.value,
    pooled: pooledBeyond(selection.selectedRows.value),
  })
}

function removeSince(signup: SharedListSignup) {
  askRemove({ kind: 'since', createdAt: signup.created_at })
}

const heading = useTemplateRef<HTMLElement>('heading')
const rowsView = useTemplateRef<{ $el: HTMLElement }>('rowsView')

const focusRows = () => firstCheckbox(rowsView.value?.$el) ?? heading.value

const selectionActions = computed<SelectionAction[]>(() => [
  { id: 'remove', label: t('sharedLists.actions.remove'), icon: UserMinus, destructive: true },
])
</script>

<template>
  <section
    class="grid gap-3"
    aria-labelledby="shared-list-signups-title"
    data-testid="shared-list-signups"
  >
    <h3
      id="shared-list-signups-title"
      ref="heading"
      tabindex="-1"
      class="text-[15px] font-bold outline-none"
    >
      {{ t('sharedLists.detail.signupsTitle') }}
    </h3>

    <div v-if="result && (result.total > 0 || q)" class="grid gap-2">
      <SearchField
        v-model="q"
        :label="t('sharedLists.search.signups')"
        :placeholder="t('sharedLists.search.signupsPlaceholder')"
      />
      <SortSelect
        v-if="isMobile"
        :options="sortOptions"
        :sort="sort"
        :dir="dir"
        @sort="(key, direction) => setSort(key, direction)"
      />
    </div>

    <p v-if="!result" class="py-3 text-sm text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>
    <p
      v-else-if="rows.length === 0"
      class="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground"
      data-testid="shared-list-signups-empty"
    >
      {{ q ? t('sharedLists.signups.emptySearch', { q }) : t('sharedLists.signups.empty') }}
    </p>
    <template v-else>
      <SharedListSignupsCardList
        v-if="isMobile"
        ref="rowsView"
        :rows="rows"
        :selection="selection"
        :loading="store.signupsLoading"
        @remove="removeOne"
        @remove-since="removeSince"
      />
      <SharedListSignupsTable
        v-else
        ref="rowsView"
        :rows="rows"
        :selection="selection"
        :sort="sort"
        :dir="dir"
        :loading="store.signupsLoading"
        @sort="setSort"
        @remove="removeOne"
        @remove-since="removeSince"
      />
    </template>

    <p
      v-if="result && result.hidden_count > 0"
      class="text-[13px] text-muted-foreground"
      data-testid="shared-list-signups-hidden"
    >
      {{ t('sharedLists.signups.hidden', { count: result.hidden_count }, result.hidden_count) }}
    </p>

    <SelectionBar
      :count="selection.count.value"
      :actions="selectionActions"
      :label="t('sharedLists.signups.region')"
      placement="dialog"
      :focus-on-leave="focusRows"
      @action="removeSelected"
      @clear="selection.clear()"
    />

    <ListPagination
      v-if="result"
      v-model:page="page"
      :total="result.total"
      :page-size="table.pageSize"
    />

    <SharedListRemoveSignupsDialog
      v-model:open="removeOpen"
      :list-id="props.listId"
      :target="removeTarget"
      :can-erase="result?.can_erase ?? false"
      @done="selection.clear()"
      @refocus="heading?.focus()"
    />
  </section>
</template>
