<script setup lang="ts">
/**
 * The lists of an event as cards, for a phone: the same facts as the table,
 * stacked, with a checkbox for the bulk actions and a ⋯ menu in place of the
 * row's icon buttons. The sort control sits above the list, outside it.
 */
import { useI18n } from 'vue-i18n'

import type { ListAction } from '@/stores/sharedLists'

import type { RowSelection } from '@/composables/useRowSelection'

import { Checkbox } from '@/components/ui/checkbox'

import FillBar from '@/components/data-table/FillBar.vue'
import SharedListIssueStrip from '@/components/shared-lists/SharedListIssueStrip.vue'
import SharedListRowActions from '@/components/shared-lists/SharedListRowActions.vue'
import SharedListTitleBlock from '@/components/shared-lists/SharedListTitleBlock.vue'
import { useSharedListText } from '@/components/shared-lists/sharedListText'
import { isListSelectable } from '@/components/shared-lists/useSharedListActions'

import type { SharedListRow } from '@/client/types.gen'

const props = defineProps<{
  rows: readonly SharedListRow[]
  zone: string
  selection: RowSelection<SharedListRow>
  busyId: string | null
  copiedId: string | null
  /** The viewer may pause but not reopen or extend (`reshareLocked`). */
  locked?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  open: [row: SharedListRow]
  copy: [row: SharedListRow]
  act: [row: SharedListRow, action: ListAction]
}>()

const { t } = useI18n()
const { closesText } = useSharedListText()
</script>

<template>
  <ul
    class="grid gap-2.5"
    :aria-label="t('sharedLists.table.caption')"
    :aria-busy="props.loading || undefined"
    data-testid="shared-lists-cards"
  >
    <li
      v-for="row in props.rows"
      :key="row.id"
      class="rounded-xl border bg-card py-3 pr-1 pl-1"
      :class="[
        row.issue ? 'border-warning/50' : '',
        props.selection.isSelected(row.id) ? 'ring-1 ring-primary' : '',
      ]"
      :data-list-id="row.id"
      :data-testid="`shared-list-row-${row.id}`"
    >
      <div class="flex items-start gap-1">
        <!-- The label gives the small box a thumb-sized target. -->
        <label class="flex size-11 shrink-0 items-center justify-center">
          <Checkbox
            :model-value="props.selection.isSelected(row.id)"
            :disabled="!isListSelectable(row)"
            :aria-label="t('sharedLists.table.selectRow', { title: row.title })"
            data-testid="shared-list-select"
            @update:model-value="(value) => props.selection.toggle(row.id, value === true)"
          />
        </label>
        <div class="grid min-w-0 flex-1 gap-2.5 pt-2.5">
          <SharedListTitleBlock
            :row="row"
            :zone="props.zone"
            with-status
            @open="emit('open', row)"
          />
          <div class="flex items-center gap-4">
            <FillBar class="flex-1" :free="row.free" :cap="row.capacity" />
            <p class="shrink-0 text-right text-[13px] text-muted-foreground">
              <span class="text-base font-bold text-foreground tabular-nums">
                {{ row.signup_count }}
              </span>
              {{ t('sharedLists.rows.signedUp') }}
            </p>
          </div>
          <p class="text-xs text-muted-foreground">
            {{ t('sharedLists.rows.openUntil', { when: closesText(row) }) }}
          </p>
          <SharedListIssueStrip
            v-if="row.issue"
            :issue="row.issue"
            :title="row.title"
            :status="row.effective_status"
            :busy="props.busyId === row.id"
            :locked="props.locked"
            @fix="emit('act', row, $event)"
          />
        </div>
        <SharedListRowActions
          :row="row"
          variant="menu"
          :busy="props.busyId === row.id"
          :copied="props.copiedId === row.id"
          :locked="props.locked"
          @copy="emit('copy', row)"
          @pause="emit('act', row, 'pause')"
          @resume="emit('act', row, 'resume')"
          @open="emit('open', row)"
        />
      </div>
    </li>
  </ul>
</template>
