<script setup lang="ts">
/**
 * What the people running a list can do with it, under the heading of its page.
 *
 * An ended list can only be shared again, as a new list. Otherwise: pause, or
 * resume ("reopen" once expired), edit, give it a new link, end it. On a wide
 * screen these are buttons; on a phone the first stays a button and the rest
 * go into a ⋯ menu, whose items run once it has closed and handed focus back
 * to its button (`useMenuAction`), because two of them ask first.
 *
 * `locked` is a person in charge after the event admins turned sharing off:
 * they may still pause and end, nothing else.
 *
 * While a change runs, the buttons are `aria-disabled`, not disabled: the one
 * pressed keeps focus, which a disabled button would drop to <body>. Ending the list swaps the buttons for "Share again",
 * which takes focus over.
 */
import { computed, nextTick, useTemplateRef, watch } from 'vue'

import { CircleStop, Ellipsis, Pause, Pencil, Play, RefreshCw, Share2 } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import type { ListAction } from '@/stores/sharedLists'

import { useMenuAction } from '@/composables/useMenuAction'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { RESPONSIVE_DIALOG_MOBILE_QUERY } from '@/components/ui/responsive-dialog'

import { resumeLabelKey } from '@/components/shared-lists/useSharedListActions'

import type { SharedListDetail } from '@/client/types.gen'

const props = defineProps<{
  list: Pick<SharedListDetail, 'effective_status'>
  /** A change is running. */
  busy?: boolean
  locked?: boolean
}>()

const emit = defineEmits<{
  act: [action: ListAction]
  edit: []
  shareAgain: []
}>()

const { t } = useI18n()
const isMobile = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)
const menu = useMenuAction()

const ended = computed(() => props.list.effective_status === 'ended')
const live = computed(() => props.list.effective_status === 'live')

/** Pausing an open list, or resuming one that is not: the main action. */
const toggle = computed(() =>
  live.value
    ? { action: 'pause' as const, label: t('sharedLists.actions.pause'), icon: Pause }
    : {
        action: 'resume' as const,
        label: t(resumeLabelKey(props.list.effective_status)),
        icon: Play,
      },
)
/** The toggle cannot be used now; it stays focusable all the same. */
const toggleInert = computed(() => props.busy || (!live.value && props.locked))

function act(action: ListAction, inert: boolean) {
  if (!inert) emit('act', action)
}

const root = useTemplateRef<HTMLElement>('root')

/** The first button: the toggle, or "Share again" once the list has ended. */
function focusMain(): void {
  root.value?.querySelector<HTMLElement>('button')?.focus()
}

// Ending removes the button that did it (and the ⋯ menu's).
watch(ended, async (now) => {
  if (!now || !root.value?.contains(document.activeElement)) return
  await nextTick()
  focusMain()
})

defineExpose({ focusMain })
</script>

<template>
  <div
    ref="root"
    class="flex flex-wrap items-center gap-2"
    data-testid="shared-list-detail-actions"
  >
    <template v-if="ended">
      <Button
        :disabled="props.locked"
        class="max-md:h-11"
        data-testid="shared-list-detail-share-again"
        @click="emit('shareAgain')"
      >
        <Share2 aria-hidden="true" />
        {{ t('sharedLists.actions.shareAgain') }}
      </Button>
      <p class="min-w-0 max-w-xs flex-1 basis-48 text-[13px] text-muted-foreground">
        {{ t('sharedLists.detail.shareAgainHint') }}
      </p>
    </template>

    <template v-else-if="isMobile">
      <Button
        class="h-11 flex-1 aria-disabled:opacity-50"
        :variant="live ? 'outline' : 'default'"
        :aria-disabled="toggleInert || undefined"
        :data-testid="`shared-list-detail-${toggle.action}`"
        @click="act(toggle.action, toggleInert)"
      >
        <component :is="toggle.icon" aria-hidden="true" />
        {{ toggle.label }}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button
            variant="outline"
            size="icon"
            class="size-11 shrink-0"
            :aria-label="t('sharedLists.detail.moreActions')"
            data-testid="shared-list-detail-more"
          >
            <Ellipsis aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" @close-auto-focus="menu.onCloseAutoFocus">
          <DropdownMenuItem
            :disabled="props.locked"
            data-testid="shared-list-detail-edit"
            @select="menu.after(() => emit('edit'))"
          >
            <Pencil aria-hidden="true" />
            {{ t('sharedLists.actions.edit') }}
          </DropdownMenuItem>
          <DropdownMenuItem
            :disabled="props.locked || props.busy"
            data-testid="shared-list-detail-rotate"
            @select="menu.after(() => emit('act', 'rotate'))"
          >
            <RefreshCw aria-hidden="true" />
            {{ t('sharedLists.actions.rotate') }}
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            :disabled="props.busy"
            data-testid="shared-list-detail-end"
            @select="menu.after(() => emit('act', 'end'))"
          >
            <CircleStop aria-hidden="true" />
            {{ t('sharedLists.actions.end') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>

    <template v-else>
      <Button
        class="aria-disabled:opacity-50"
        :variant="live ? 'outline' : 'default'"
        :aria-disabled="toggleInert || undefined"
        :data-testid="`shared-list-detail-${toggle.action}`"
        @click="act(toggle.action, toggleInert)"
      >
        <component :is="toggle.icon" aria-hidden="true" />
        {{ toggle.label }}
      </Button>
      <Button
        variant="outline"
        :disabled="props.locked"
        data-testid="shared-list-detail-edit"
        @click="emit('edit')"
      >
        <Pencil aria-hidden="true" />
        {{ t('sharedLists.actions.edit') }}
      </Button>
      <Button
        variant="outline"
        class="aria-disabled:opacity-50"
        :disabled="props.locked"
        :aria-disabled="props.busy || undefined"
        data-testid="shared-list-detail-rotate"
        @click="act('rotate', props.busy)"
      >
        <RefreshCw aria-hidden="true" />
        {{ t('sharedLists.actions.rotate') }}
      </Button>
      <Button
        variant="outline"
        class="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive aria-disabled:opacity-50"
        :aria-disabled="props.busy || undefined"
        data-testid="shared-list-detail-end"
        @click="act('end', props.busy)"
      >
        <CircleStop aria-hidden="true" />
        {{ t('sharedLists.actions.end') }}
      </Button>
    </template>
  </div>
</template>
