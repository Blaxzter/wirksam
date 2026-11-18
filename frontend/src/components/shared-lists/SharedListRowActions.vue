<script setup lang="ts">
/**
 * A list's own buttons in its row: copy the link, pause or resume, details.
 *
 * `icons` is the desktop row, icon buttons with a hint each. `menu` is the
 * phone card's ⋯ menu; "Details" opens a dialog, so it runs once the menu has
 * closed and handed focus back to its button (`useMenuAction`), where the
 * dialog returns it.
 *
 * Copying is offered unless the list has ended; pausing and resuming only to
 * those who may manage it, and resuming not while sharing is locked for them.
 * While a change runs, or once the toggle has turned into a "resume" the
 * viewer may not use, it is `aria-disabled` rather than disabled, so it keeps
 * the focus it had.
 */
import { computed } from 'vue'

import { Check, ChevronRight, Copy, Ellipsis, Pause, Play } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useMenuAction } from '@/composables/useMenuAction'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import { canManageList, resumeLabelKey } from '@/components/shared-lists/useSharedListActions'
import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { SharedListRow } from '@/client/types.gen'

const props = defineProps<{
  row: SharedListRow
  variant: 'icons' | 'menu'
  /** A change is running for this list. */
  busy?: boolean
  /** Its link was just copied: the copy button shows a tick. */
  copied?: boolean
  /** The viewer may pause it but not reopen it (`reshareLocked`). */
  locked?: boolean
}>()

const emit = defineEmits<{
  copy: []
  pause: []
  resume: []
  open: []
}>()

const { t } = useI18n()
const menu = useMenuAction()

const ended = computed(() => props.row.effective_status === 'ended')
const live = computed(() => props.row.effective_status === 'live')
const mayManage = computed(() => canManageList(props.row))
/** The toggle cannot be used now, though it may have focus. */
const toggleInert = computed(() => props.busy || (!live.value && props.locked))

/** Pause for an open list, resume for one that is not; nothing once it has ended. */
const toggle = computed(() => {
  if (ended.value) return null
  return live.value
    ? { event: 'pause' as const, label: t('sharedLists.actions.pause'), icon: Pause }
    : {
        event: 'resume' as const,
        label: t(resumeLabelKey(props.row.effective_status)),
        icon: Play,
      }
})

function runToggle() {
  if (!mayManage.value || toggleInert.value) return
  if (toggle.value?.event === 'pause') emit('pause')
  else emit('resume')
}

const copyLabel = computed(() => t('sharedLists.actions.copyLink'))
const detailsLabel = computed(() => t('sharedLists.actions.details'))
</script>

<template>
  <div
    v-if="props.variant === 'icons'"
    class="flex items-center justify-end gap-0.5"
    data-testid="shared-list-actions"
  >
    <HintTooltip :label="copyLabel">
      <span class="inline-flex">
        <Button
          variant="ghost"
          size="icon"
          :disabled="ended"
          :aria-label="`${copyLabel}: ${props.row.title}`"
          data-testid="shared-list-copy"
          @click="emit('copy')"
        >
          <Check v-if="props.copied" class="text-primary" aria-hidden="true" />
          <Copy v-else aria-hidden="true" />
        </Button>
      </span>
    </HintTooltip>
    <HintTooltip v-if="toggle" :label="toggle.label">
      <span class="inline-flex">
        <Button
          variant="ghost"
          size="icon"
          class="aria-disabled:opacity-50"
          :disabled="!mayManage"
          :aria-disabled="toggleInert || undefined"
          :aria-label="`${toggle.label}: ${props.row.title}`"
          :data-testid="`shared-list-${toggle.event}`"
          @click="runToggle"
        >
          <component :is="toggle.icon" aria-hidden="true" />
        </Button>
      </span>
    </HintTooltip>
    <HintTooltip :label="detailsLabel">
      <Button
        variant="ghost"
        size="icon"
        :aria-label="`${detailsLabel}: ${props.row.title}`"
        data-testid="shared-list-details"
        @click="emit('open')"
      >
        <ChevronRight aria-hidden="true" />
      </Button>
    </HintTooltip>
  </div>

  <DropdownMenu v-else>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="size-11 shrink-0"
        :aria-label="t('sharedLists.rows.menu', { title: props.row.title })"
        data-testid="shared-list-menu"
      >
        <Ellipsis aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" @close-auto-focus="menu.onCloseAutoFocus">
      <DropdownMenuItem :disabled="ended" data-testid="shared-list-copy" @select="emit('copy')">
        <Copy aria-hidden="true" />
        {{ copyLabel }}
      </DropdownMenuItem>
      <DropdownMenuItem
        v-if="toggle"
        :disabled="!mayManage || toggleInert"
        :data-testid="`shared-list-${toggle.event}`"
        @select="runToggle"
      >
        <component :is="toggle.icon" aria-hidden="true" />
        {{ toggle.label }}
      </DropdownMenuItem>
      <DropdownMenuItem data-testid="shared-list-details" @select="menu.after(() => emit('open'))">
        <ChevronRight aria-hidden="true" />
        {{ detailsLabel }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
