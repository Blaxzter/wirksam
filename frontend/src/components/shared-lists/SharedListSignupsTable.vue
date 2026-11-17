<script setup lang="ts">
/**
 * Who signed up through a list, as a table in its details on a wide screen:
 * sortable by name, shift and when, with a checkbox per sign-up that can
 * still be removed (its shift is not over), "Remove" and a ⋯ menu for
 * "this and every newer one".
 */
import { useI18n } from 'vue-i18n'

import type { SignupSort } from '@/stores/sharedLists'

import type { RowSelection } from '@/composables/useRowSelection'
import type { SortDir } from '@/composables/useTableQuery'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import SortableHead from '@/components/data-table/SortableHead.vue'
import TableCard from '@/components/data-table/TableCard.vue'
import TriStateCheckbox from '@/components/data-table/TriStateCheckbox.vue'
import SharedListSignupMenu from '@/components/shared-lists/SharedListSignupMenu.vue'
import SharedListSignupPerson from '@/components/shared-lists/SharedListSignupPerson.vue'
import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListSignup } from '@/client/types.gen'

const props = defineProps<{
  rows: readonly SharedListSignup[]
  selection: RowSelection<SharedListSignup>
  sort: SignupSort
  dir: SortDir
  loading?: boolean
}>()

const emit = defineEmits<{
  sort: [key: SignupSort]
  remove: [signup: SharedListSignup]
  removeSince: [signup: SharedListSignup]
}>()

const { t } = useI18n()
const { shiftText, signedUpWhen, signupLabel } = useSharedListText()
</script>

<template>
  <TableCard>
    <Table :aria-busy="props.loading || undefined" data-testid="shared-list-signups-table">
      <caption class="sr-only">
        {{
          t('sharedLists.signups.caption')
        }}
      </caption>
      <TableHeader>
        <TableRow class="hover:bg-transparent">
          <TableHead class="w-10">
            <TriStateCheckbox
              :model-value="props.selection.headerState.value"
              :disabled="!props.selection.canSelect.value"
              :aria-label="t('sharedLists.signups.selectAll')"
              data-testid="shared-list-signups-select-all"
              @update:model-value="(value) => props.selection.toggleAll(value === true)"
            />
          </TableHead>
          <SortableHead
            :label="t('sharedLists.signups.columns.name')"
            sort-key="name"
            :active-key="props.sort"
            :dir="props.dir"
            @sort="emit('sort', $event)"
          />
          <SortableHead
            :label="t('sharedLists.signups.columns.shift')"
            sort-key="shift_start"
            :active-key="props.sort"
            :dir="props.dir"
            @sort="emit('sort', $event)"
          />
          <SortableHead
            :label="t('sharedLists.signups.columns.when')"
            sort-key="created_at"
            :active-key="props.sort"
            :dir="props.dir"
            default-dir="desc"
            @sort="emit('sort', $event)"
          />
          <TableHead class="w-px">
            <span class="sr-only">{{ t('sharedLists.table.columns.actions') }}</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow
          v-for="row in props.rows"
          :key="row.booking_id"
          :data-state="props.selection.isSelected(row.booking_id) ? 'selected' : undefined"
          data-testid="shared-list-signup"
        >
          <TableCell class="align-top">
            <Checkbox
              class="mt-1"
              :model-value="props.selection.isSelected(row.booking_id)"
              :disabled="!row.can_remove"
              :aria-label="t('sharedLists.signups.selectRow', { name: signupLabel(row) })"
              data-testid="shared-list-signup-select"
              @update:model-value="
                (value) => props.selection.toggle(row.booking_id, value === true)
              "
            />
          </TableCell>
          <TableCell class="align-top">
            <SharedListSignupPerson :signup="row" />
          </TableCell>
          <TableCell class="align-top text-[13px] whitespace-normal">
            <span class="font-medium">{{ row.task_name }}</span>
            <span class="block text-muted-foreground">
              {{ shiftText(row.shift_date, row.start_time, row.end_time) }}
            </span>
          </TableCell>
          <TableCell class="align-top text-[13px] text-muted-foreground">
            {{ signedUpWhen(row.created_at) }}
          </TableCell>
          <TableCell class="align-top">
            <div v-if="row.can_remove" class="flex items-center justify-end gap-0.5">
              <Button
                variant="ghost"
                size="sm"
                :aria-label="t('sharedLists.signups.removeRow', { name: signupLabel(row) })"
                data-testid="shared-list-signup-remove"
                @click="emit('remove', row)"
              >
                {{ t('sharedLists.actions.remove') }}
              </Button>
              <SharedListSignupMenu
                :name="signupLabel(row)"
                @remove-since="emit('removeSince', row)"
              />
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </TableCard>
</template>
