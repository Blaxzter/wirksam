import { computed, shallowRef } from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type {
  EventRead,
  SharedListCandidate,
  SharedListCandidateListResponse,
  SharedListCandidateShift,
  SharedListCreate,
  SharedListDetail,
  SharedListUpdate,
} from '@/client/types.gen'

/** The most `GET …/candidates` returns per page. */
export const CANDIDATE_PAGE_SIZE = 50
/** The most task ids `GET …/candidate-shifts` takes in one request. */
export const SHIFT_TASKS_PER_REQUEST = 50
/** A stop for looking up picked tasks page by page, should a server never run out. */
const MAX_CANDIDATE_PAGES = 20

/**
 * The requests behind the shared-list wizard, and the shifts it has loaded.
 *
 * Shifts are kept per task for as long as the wizard is open: taking a task
 * out and back in, or ticking days, never asks again, and a request still in
 * flight is not sent twice.
 */
export function useSharedListWizardApi() {
  const { get, post, patch } = useAuthenticatedClient()

  async function fetchEvent(eventId: string): Promise<EventRead> {
    const res = await get<{ data: EventRead }>({ url: `/events/${eventId}` })
    return res.data
  }

  /** One page of the tasks the caller may put on a list; `q` searches name and place. */
  async function fetchCandidates(
    eventId: string,
    options: { q?: string; skip?: number } = {},
  ): Promise<SharedListCandidateListResponse> {
    const res = await get<{ data: SharedListCandidateListResponse }>({
      url: `/events/${eventId}/shared-lists/candidates`,
      query: {
        q: options.q || undefined,
        skip: options.skip ?? 0,
        limit: CANDIDATE_PAGE_SIZE,
      },
    })
    return res.data
  }

  /**
   * The candidates with these ids, in the order asked for, for tasks picked
   * elsewhere (`?tasks=`). Ids the caller may not share, or that cannot go on
   * a list, are not found and left out.
   */
  async function findCandidates(
    eventId: string,
    ids: readonly string[],
  ): Promise<SharedListCandidate[]> {
    const wanted = new Set(ids)
    const found = new Map<string, SharedListCandidate>()
    for (let page = 0; page < MAX_CANDIDATE_PAGES && found.size < wanted.size; page += 1) {
      const res = await fetchCandidates(eventId, { skip: page * CANDIDATE_PAGE_SIZE })
      for (const item of res.items) if (wanted.has(item.id)) found.set(item.id, item)
      if ((page + 1) * CANDIDATE_PAGE_SIZE >= res.total) break
    }
    return ids.flatMap((id) => found.get(id) ?? [])
  }

  /** The not-started shifts of these tasks, asking in batches the API accepts. */
  async function fetchCandidateShifts(
    eventId: string,
    taskIds: readonly string[],
  ): Promise<SharedListCandidateShift[]> {
    const batches: string[][] = []
    for (let i = 0; i < taskIds.length; i += SHIFT_TASKS_PER_REQUEST) {
      batches.push(taskIds.slice(i, i + SHIFT_TASKS_PER_REQUEST))
    }
    const pages = await Promise.all(
      batches.map((batch) =>
        get<{ data: SharedListCandidateShift[] }>({
          url: `/events/${eventId}/shared-lists/candidate-shifts`,
          query: { task_id: batch },
        }),
      ),
    )
    return pages.flatMap((res) => res.data)
  }

  async function fetchDetail(listId: string): Promise<SharedListDetail> {
    const res = await get<{ data: SharedListDetail }>({ url: `/shared-lists/${listId}` })
    return res.data
  }

  async function create(eventId: string, body: SharedListCreate): Promise<SharedListDetail> {
    const res = await post<{ data: SharedListDetail }>({
      url: `/events/${eventId}/shared-lists`,
      body,
    })
    return res.data
  }

  async function update(listId: string, body: SharedListUpdate): Promise<SharedListDetail> {
    const res = await patch<{ data: SharedListDetail }>({
      url: `/shared-lists/${listId}`,
      body,
    })
    return res.data
  }

  // --- Shifts per task ----------------------------------------------------

  const shiftsByTask = shallowRef<ReadonlyMap<string, readonly SharedListCandidateShift[]>>(
    new Map(),
  )
  const pendingTasks = shallowRef<ReadonlySet<string>>(new Set())
  const shiftsError = shallowRef<unknown>(null)
  const shiftsLoading = computed(() => pendingTasks.value.size > 0)

  /** Load the shifts of whichever of `taskIds` are neither known nor on their way. */
  async function loadShifts(eventId: string, taskIds: readonly string[]): Promise<void> {
    const missing = taskIds.filter(
      (id) => !shiftsByTask.value.has(id) && !pendingTasks.value.has(id),
    )
    if (missing.length === 0) return
    pendingTasks.value = new Set([...pendingTasks.value, ...missing])
    try {
      const shifts = await fetchCandidateShifts(eventId, missing)
      const next = new Map(shiftsByTask.value)
      for (const id of missing) {
        next.set(
          id,
          shifts.filter((s) => s.task_id === id),
        )
      }
      shiftsByTask.value = next
      shiftsError.value = null
    } catch (error) {
      shiftsError.value = error
    } finally {
      const rest = new Set(pendingTasks.value)
      for (const id of missing) rest.delete(id)
      pendingTasks.value = rest
    }
  }

  return {
    fetchEvent,
    fetchCandidates,
    findCandidates,
    fetchCandidateShifts,
    fetchDetail,
    create,
    update,
    shiftsByTask: computed(() => shiftsByTask.value),
    shiftsLoading,
    shiftsError: computed(() => shiftsError.value),
    loadShifts,
  }
}
