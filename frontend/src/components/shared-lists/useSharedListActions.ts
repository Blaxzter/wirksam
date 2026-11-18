import { ref } from 'vue'

import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { type ListAction, type ListSort, useSharedListsStore } from '@/stores/sharedLists'

import { useClipboardCopy } from '@/composables/useClipboardCopy'
import type { SortDir } from '@/composables/useTableQuery'

import type { SharedListRow } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { sharedListUrl } from '@/lib/shared-lists'

/**
 * From here the page shows tables, below it cards. Wider than the `md` line
 * the dialogs use: the sidebar takes 16rem from `md` up, and a table of lists
 * needs the room that leaves only from `lg`.
 */
export const WIDE_TABLE_QUERY = '(min-width: 1024px)'

type ListRef = Pick<SharedListRow, 'id' | 'title' | 'effective_status'>

/** Whether the list can be managed by the viewer at all (not just read). */
export function canManageList(list: Pick<SharedListRow, 'access'>): boolean {
  return list.access === 'admin' || list.access === 'manager'
}

/** A row the bulk actions may take: one the viewer manages that has not ended. */
export function isListSelectable(
  list: Pick<SharedListRow, 'access' | 'effective_status'>,
): boolean {
  return canManageList(list) && list.effective_status !== 'ended'
}

/** The order each column of the lists table starts in, as the server sorts it by default. */
export const LIST_SORT_DIRS: Partial<Record<ListSort, SortDir>> = {
  created_at: 'desc',
  signups: 'desc',
  free: 'desc',
}

/** Resuming an expired list reopens it until its last shift; the button says so. */
export function resumeLabelKey(status: SharedListRow['effective_status']): string {
  return status === 'expired' ? 'sharedLists.actions.reopen' : 'sharedLists.actions.resume'
}

/** The fix an issue strip offers, and how its button reads. */
export function issueFix(
  row: Pick<SharedListRow, 'issue' | 'effective_status'>,
): { action: ListAction; labelKey: string } | null {
  if (!row.issue) return null
  if (row.issue.kind === 'expires_soon') {
    return { action: 'extend', labelKey: 'sharedLists.actions.extend' }
  }
  return { action: 'resume', labelKey: resumeLabelKey(row.effective_status) }
}

function successKey(list: ListRef, action: ListAction): string {
  if (action === 'resume' && list.effective_status === 'expired') {
    return 'sharedLists.toasts.reopened'
  }
  const keys: Record<ListAction, string> = {
    pause: 'sharedLists.toasts.paused',
    resume: 'sharedLists.toasts.resumed',
    end: 'sharedLists.toasts.ended',
    rotate: 'sharedLists.toasts.rotated',
    extend: 'sharedLists.toasts.extended',
  }
  return keys[action]
}

/**
 * What a list's own buttons do, wherever they sit (a table row, a card, the
 * details): copy its link, and pause, resume, end, extend or renew it, each
 * with the toast that says what happened. `busyId` is the list a change is
 * running for, `copiedId` the one whose link was just copied.
 */
export function useSharedListActions() {
  const { t } = useI18n()
  const store = useSharedListsStore()

  const busyId = ref<string | null>(null)
  const { copied: copiedId, copy } = useClipboardCopy<string>()

  async function copyLink(list: Pick<SharedListRow, 'id' | 'code'>) {
    const url = sharedListUrl(list.code)
    if (await copy(list.id, url)) {
      toast.success(t('sharedLists.toasts.copied'))
    } else {
      // A blocked clipboard: show the link so it can still be copied by hand.
      toast.info(url)
    }
  }

  /** Resolves to whether it worked; a refusal has been toasted already. */
  async function run(list: ListRef, action: ListAction): Promise<boolean> {
    busyId.value = list.id
    try {
      await store.act(list.id, action)
      toast.success(t(successKey(list, action), { title: list.title }))
      return true
    } catch (error) {
      toastApiError(error)
      return false
    } finally {
      busyId.value = null
    }
  }

  return { busyId, copiedId, copyLink, run }
}
