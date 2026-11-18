<script setup lang="ts">
/**
 * Who signed up through a list, in its details on a phone: one row per
 * sign-up with the person, the shift and when, a checkbox, and a ⋯ menu to
 * take it (or it and every newer one) off.
 */
import { useI18n } from 'vue-i18n'

import type { RowSelection } from '@/composables/useRowSelection'

import { Checkbox } from '@/components/ui/checkbox'

import SharedListSignupMenu from '@/components/shared-lists/SharedListSignupMenu.vue'
import SharedListSignupPerson from '@/components/shared-lists/SharedListSignupPerson.vue'
import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListSignup } from '@/client/types.gen'

const props = defineProps<{
  rows: readonly SharedListSignup[]
  selection: RowSelection<SharedListSignup>
  loading?: boolean
}>()

const emit = defineEmits<{
  remove: [signup: SharedListSignup]
  removeSince: [signup: SharedListSignup]
}>()

const { t } = useI18n()
const { signedUpWhen, signupLabel } = useSharedListText()
</script>

<template>
  <ul
    class="divide-y rounded-xl border bg-card"
    :aria-label="t('sharedLists.signups.caption')"
    :aria-busy="props.loading || undefined"
    data-testid="shared-list-signups-cards"
  >
    <li
      v-for="row in props.rows"
      :key="row.booking_id"
      class="flex items-start gap-1 py-2 pr-1 pl-0.5"
      data-testid="shared-list-signup"
    >
      <label class="flex size-11 shrink-0 items-center justify-center">
        <Checkbox
          :model-value="props.selection.isSelected(row.booking_id)"
          :disabled="!row.can_remove"
          :aria-label="t('sharedLists.signups.selectRow', { name: signupLabel(row) })"
          data-testid="shared-list-signup-select"
          @update:model-value="(value) => props.selection.toggle(row.booking_id, value === true)"
        />
      </label>
      <div class="grid min-w-0 flex-1 gap-0.5 pt-2">
        <SharedListSignupPerson :signup="row" with-shift />
        <p class="text-xs text-muted-foreground">{{ signedUpWhen(row.created_at) }}</p>
      </div>
      <SharedListSignupMenu
        v-if="row.can_remove"
        :name="signupLabel(row)"
        with-remove
        @remove="emit('remove', row)"
        @remove-since="emit('removeSince', row)"
      />
    </li>
  </ul>
</template>
