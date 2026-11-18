import { computed, ref } from 'vue'

import { defineStore } from 'pinia'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import type { TableParams } from '@/composables/useTableQuery'

import type {
  PublicSharedList,
  SharedListBulkRequest,
  SharedListBulkResult,
  SharedListDetail,
  SharedListGuestsListSharedListSignupsData,
  SharedListListResponse,
  SharedListOverview,
  SharedListRow,
  SharedListSignupListResponse,
  SharedListSignupRemoveRequest,
  SharedListSignupRemoveResult,
  SharedListTaskListResponse,
  SharedListsListSharedListTasksData,
  SharedListsListSharedListsData,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

type ListQuery = NonNullable<SharedListsListSharedListsData['query']>
type TaskQuery = NonNullable<SharedListsListSharedListTasksData['query']>
type SignupQuery = NonNullable<SharedListGuestsListSharedListSignupsData['query']>

export type ListFilter = NonNullable<ListQuery['status_filter']>
export type ListSort = NonNullable<ListQuery['sort_by']>
export type TaskFilter = NonNullable<TaskQuery['status_filter']>
export type TaskSort = NonNullable<TaskQuery['sort_by']>
export type SignupSort = NonNullable<SignupQuery['sort_by']>
export type BulkAction = SharedListBulkRequest['action']
/** What one list's own buttons do; `extend` keeps it open until its last shift. */
export type ListAction = 'pause' | 'resume' | 'end' | 'rotate' | 'extend'

export type ListParams = TableParams<ListSort, ListFilter>
export type TaskParams = TableParams<TaskSort, TaskFilter>
export type SignupParams = TableParams<SignupSort, never>

/** The most lists the list endpoint returns at once, which the preview's picker asks for. */
export const PREVIEW_CHOICES_LIMIT = 100

/**
 * Drops answers that arrive after a newer request for the same thing: a quick
 * second click on a sort header must not be overwritten by the first one's
 * late answer, nor a list of the event just left by its own.
 */
function newestOnly() {
  let current = 0
  return {
    start: () => ++current,
    isCurrent: (ticket: number) => ticket === current,
  }
}

/**
 * The management page of one event's shared lists: its figures, the current
 * page of each table, the list whose details are open and its sign-ups.
 *
 * Every change goes through here and reloads what is on screen afterwards,
 * because one pause moves the figures, the chip counts, the "to do" rows and
 * the tasks tab at once. A reload that fails keeps the old page and says so.
 */
export const useSharedListsStore = defineStore('sharedLists', () => {
  const { get, post, patch } = useAuthenticatedClient()

  const eventId = ref<string | null>(null)
  const overview = ref<SharedListOverview | null>(null)
  const lists = ref<SharedListListResponse | null>(null)
  const tasks = ref<SharedListTaskListResponse | null>(null)
  const detail = ref<SharedListDetail | null>(null)
  const signups = ref<SharedListSignupListResponse | null>(null)

  const listsLoading = ref(false)
  const tasksLoading = ref(false)
  const signupsLoading = ref(false)

  /**
   * The viewer is in charge of tasks, not an event admin, and the admins have
   * turned sharing off for such people: they may still pause and end their
   * lists, but not reopen, extend, edit, renew or create one.
   */
  const reshareLocked = computed(
    () => !!overview.value && !overview.value.is_admin && !overview.value.managers_share_lists,
  )

  // The last request per table, so a change can reload the same page.
  let listsQuery: ListParams | null = null
  let tasksQuery: TaskParams | null = null
  let signupsQuery: SignupParams | null = null

  const order = {
    overview: newestOnly(),
    lists: newestOnly(),
    tasks: newestOnly(),
    detail: newestOnly(),
    signups: newestOnly(),
  }

  function requireEvent(): string {
    if (!eventId.value) throw new Error('No event chosen for shared lists')
    return eventId.value
  }

  /** Point the store at another event, forgetting everything of the last one. */
  function setEvent(id: string | null) {
    if (id === eventId.value) return
    eventId.value = id
    overview.value = null
    lists.value = null
    tasks.value = null
    listsQuery = null
    tasksQuery = null
    listsLoading.value = false
    tasksLoading.value = false
    for (const queue of Object.values(order)) queue.start()
    closeDetail()
  }

  async function fetchOverview(): Promise<SharedListOverview> {
    const ticket = order.overview.start()
    const res = await get<{ data: SharedListOverview }>({
      url: `/events/${requireEvent()}/shared-lists/overview`,
    })
    if (order.overview.isCurrent(ticket)) overview.value = res.data
    return res.data
  }

  async function fetchLists(params: ListParams): Promise<SharedListListResponse> {
    const ticket = order.lists.start()
    listsQuery = params
    listsLoading.value = true
    try {
      const res = await get<{ data: SharedListListResponse }>({
        url: `/events/${requireEvent()}/shared-lists`,
        query: { ...params },
      })
      if (order.lists.isCurrent(ticket)) lists.value = res.data
      return res.data
    } finally {
      if (order.lists.isCurrent(ticket)) listsLoading.value = false
    }
  }

  async function fetchTasks(params: TaskParams): Promise<SharedListTaskListResponse> {
    const ticket = order.tasks.start()
    tasksQuery = params
    tasksLoading.value = true
    try {
      const res = await get<{ data: SharedListTaskListResponse }>({
        url: `/events/${requireEvent()}/shared-lists/tasks`,
        query: { ...params },
      })
      if (order.tasks.isCurrent(ticket)) tasks.value = res.data
      return res.data
    } finally {
      if (order.tasks.isCurrent(ticket)) tasksLoading.value = false
    }
  }

  /** Open one list's details; another list's are cleared at once, not shown meanwhile. */
  async function fetchDetail(id: string): Promise<SharedListDetail> {
    const ticket = order.detail.start()
    if (detail.value?.id !== id) {
      detail.value = null
      signups.value = null
      signupsQuery = null
    }
    const res = await get<{ data: SharedListDetail }>({ url: `/shared-lists/${id}` })
    if (order.detail.isCurrent(ticket)) detail.value = res.data
    return res.data
  }

  function closeDetail() {
    order.detail.start()
    order.signups.start()
    detail.value = null
    signups.value = null
    signupsQuery = null
    signupsLoading.value = false
  }

  async function fetchSignups(
    listId: string,
    params: SignupParams,
  ): Promise<SharedListSignupListResponse> {
    const ticket = order.signups.start()
    signupsQuery = params
    signupsLoading.value = true
    try {
      const res = await get<{ data: SharedListSignupListResponse }>({
        url: `/shared-lists/${listId}/signups`,
        query: { ...params },
      })
      if (order.signups.isCurrent(ticket)) signups.value = res.data
      return res.data
    } finally {
      if (order.signups.isCurrent(ticket)) signupsLoading.value = false
    }
  }

  /** The lists the preview tab offers: every one that is not ended. */
  async function fetchPreviewChoices(): Promise<SharedListRow[]> {
    const res = await get<{ data: SharedListListResponse }>({
      url: `/events/${requireEvent()}/shared-lists`,
      query: { status_filter: 'active', sort_by: 'title', limit: PREVIEW_CHOICES_LIMIT },
    })
    return res.data.items
  }

  /** The public page of a list as a guest would see it, without counting a view. */
  async function fetchPreview(listId: string): Promise<PublicSharedList> {
    const res = await get<{ data: PublicSharedList }>({ url: `/shared-lists/${listId}/preview` })
    return res.data
  }

  /**
   * Reload what is on screen. `detail` is left out when the change itself
   * answered with the list; `signups` only when sign-ups changed.
   */
  async function refresh(include: { detail: boolean; signups: boolean }) {
    const open = detail.value
    const reloads: Promise<unknown>[] = [fetchOverview()]
    if (listsQuery) reloads.push(fetchLists(listsQuery))
    if (tasksQuery) reloads.push(fetchTasks(tasksQuery))
    if (open && include.detail) reloads.push(fetchDetail(open.id))
    if (open && include.signups && signupsQuery) reloads.push(fetchSignups(open.id, signupsQuery))
    const failed = (await Promise.allSettled(reloads)).find(
      (result) => result.status === 'rejected',
    )
    if (failed) toastApiError(failed.reason)
  }

  /** Pause, resume, end, extend or give a new link to one list. */
  async function act(listId: string, action: ListAction): Promise<SharedListDetail> {
    const res =
      action === 'extend'
        ? await patch<{ data: SharedListDetail }>({
            url: `/shared-lists/${listId}`,
            body: { ends_mode: 'last_shift', ends_on: null },
          })
        : await post<{ data: SharedListDetail }>({ url: `/shared-lists/${listId}/${action}` })
    const answered = detail.value?.id === listId
    if (answered) {
      // Newer than any load of the details still on its way, which must not undo it.
      order.detail.start()
      detail.value = res.data
    }
    await refresh({ detail: !answered, signups: false })
    return res.data
  }

  async function bulk(action: BulkAction, listIds: string[]): Promise<SharedListBulkResult> {
    const res = await post<{ data: SharedListBulkResult }>({
      url: `/events/${requireEvent()}/shared-lists/bulk`,
      body: { action, list_ids: listIds },
    })
    await refresh({ detail: true, signups: false })
    return res.data
  }

  /** The emergency stop; `lockManagers` also stops people in charge from reopening. */
  async function pauseAll(lockManagers: boolean): Promise<SharedListBulkResult> {
    const res = await post<{ data: SharedListBulkResult }>({
      url: `/events/${requireEvent()}/shared-lists/pause-all`,
      body: { lock_managers: lockManagers },
    })
    await refresh({ detail: true, signups: false })
    return res.data
  }

  /** Whether people in charge may share their own tasks (event admins only). */
  async function setManagersShareLists(value: boolean): Promise<void> {
    await patch({ url: `/events/${requireEvent()}`, body: { managers_share_lists: value } })
    await refresh({ detail: true, signups: false })
  }

  async function removeSignups(
    listId: string,
    body: SharedListSignupRemoveRequest,
  ): Promise<SharedListSignupRemoveResult> {
    const res = await post<{ data: SharedListSignupRemoveResult }>({
      url: `/shared-lists/${listId}/signups/remove`,
      body,
    })
    await refresh({ detail: true, signups: true })
    return res.data
  }

  return {
    eventId,
    overview,
    lists,
    tasks,
    detail,
    signups,
    listsLoading,
    tasksLoading,
    signupsLoading,
    reshareLocked,
    setEvent,
    fetchOverview,
    fetchLists,
    fetchTasks,
    fetchDetail,
    closeDetail,
    fetchSignups,
    fetchPreviewChoices,
    fetchPreview,
    act,
    bulk,
    pauseAll,
    setManagersShareLists,
    removeSignups,
  }
})
