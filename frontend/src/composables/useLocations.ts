import { type MaybeRefOrGetter, ref, toValue, watch } from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type { LocationRead } from '@/client/types.gen'

/**
 * The locations of one event, shared by every picker, filter and map on the
 * page.
 *
 * One request per event: the in-flight (or settled) promise is cached at
 * module level, so a task form with three pickers and a filter menu fetch the
 * list once. Anything that changes the list — creating, renaming or deleting
 * a location — calls {@link invalidateLocations}, which drops the cache entry
 * and makes every mounted `useLocations` for that event fetch again.
 */
const cache = new Map<string, Promise<LocationRead[]>>()
// Bumped by `invalidateLocations`; every instance watches it.
const version = ref(0)

/**
 * Forget the cached list for `eventId` (or for every event when omitted) and
 * reload it wherever it is on screen.
 */
export function invalidateLocations(eventId?: string | null) {
  if (eventId) cache.delete(eventId)
  else cache.clear()
  version.value++
}

export function useLocations(eventId: MaybeRefOrGetter<string | null | undefined>) {
  const { get } = useAuthenticatedClient()

  const locations = ref<LocationRead[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)
  // Guards against an older request resolving after a newer one.
  let generation = 0

  function fetchList(id: string): Promise<LocationRead[]> {
    let pending = cache.get(id)
    if (!pending) {
      pending = get<{ data: LocationRead[] }>({ url: `/events/${id}/locations` }).then(
        (res) => res.data,
      )
      cache.set(id, pending)
      // A failure is not worth remembering; the next caller retries.
      pending.catch(() => {
        if (cache.get(id) === pending) cache.delete(id)
      })
    }
    return pending
  }

  async function load(force = false) {
    const id = toValue(eventId)
    const gen = ++generation
    if (!id) {
      locations.value = []
      loading.value = false
      error.value = null
      return
    }
    if (force) cache.delete(id)
    loading.value = true
    error.value = null
    try {
      const data = await fetchList(id)
      if (gen === generation) locations.value = data
    } catch (e) {
      if (gen === generation) {
        locations.value = []
        error.value = e
      }
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  watch([() => toValue(eventId), version], () => load(), { immediate: true })

  return {
    locations,
    loading,
    error,
    /** Fetch again, bypassing the cache (other instances keep their copy). */
    reload: () => load(true),
  }
}
