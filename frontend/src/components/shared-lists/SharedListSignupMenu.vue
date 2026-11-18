<script setup lang="ts">
/**
 * The ⋯ menu of one sign-up: take it off, or take it and every newer one off
 * (after a wave of made-up sign-ups). Both open the removal dialog once the
 * menu has closed and handed focus back to its button (`useMenuAction`).
 */
import { Ellipsis, ListX, UserMinus } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useMenuAction } from '@/composables/useMenuAction'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const props = defineProps<{
  /** Names the menu's button. */
  name: string
  /** Also "Remove", where it has no button of its own beside the menu. */
  withRemove?: boolean
}>()

const emit = defineEmits<{
  remove: []
  removeSince: []
}>()

const { t } = useI18n()
const menu = useMenuAction()
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="shrink-0 max-md:size-11"
        :aria-label="t('sharedLists.signups.menu', { name: props.name })"
        data-testid="shared-list-signup-menu"
      >
        <Ellipsis aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" @close-auto-focus="menu.onCloseAutoFocus">
      <DropdownMenuItem
        v-if="props.withRemove"
        variant="destructive"
        data-testid="shared-list-signup-remove"
        @select="menu.after(() => emit('remove'))"
      >
        <UserMinus aria-hidden="true" />
        {{ t('sharedLists.actions.remove') }}
      </DropdownMenuItem>
      <DropdownMenuItem
        variant="destructive"
        data-testid="shared-list-signup-remove-since"
        @select="menu.after(() => emit('removeSince'))"
      >
        <ListX aria-hidden="true" />
        {{ t('sharedLists.actions.removeSince') }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
