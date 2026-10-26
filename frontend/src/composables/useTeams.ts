import { type MaybeRefOrGetter, ref, toValue, watch } from 'vue'

import type { RouteLocationRaw } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type { EventTeamRead } from '@/client/types.gen'

/**
 * The teams of one event, for the task form's picker and the "join in place"
 * dialogs on locked tasks.
 *
 * Unlike locations, the list is not kept once it has arrived: it carries the
 * viewer's own status per team, which changes the moment they join, and the
 * Teams page edits it without knowing who else is listening. Only a request
 * still in flight is shared, so a page that mounts the picker and a dialog at
 * once still fetches the list once. {@link invalidateTeams} makes every
 * mounted instance fetch again.
 */
const inFlight = new Map<string, Promise<EventTeamRead[]>>()
// Bumped by `invalidateTeams`; every instance watches it.
const version = ref(0)

/**
 * Reload the teams of `eventId` (or of every event when omitted) wherever
 * they are on screen.
 */
export function invalidateTeams(eventId?: string | null) {
  if (eventId) inFlight.delete(eventId)
  else inFlight.clear()
  version.value++
}

export function useTeams(eventId: MaybeRefOrGetter<string | null | undefined>) {
  const { get } = useAuthenticatedClient()

  const teams = ref<EventTeamRead[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)
  // Guards against an older request resolving after a newer one.
  let generation = 0

  function fetchList(id: string): Promise<EventTeamRead[]> {
    let pending = inFlight.get(id)
    if (!pending) {
      pending = get<{ data: EventTeamRead[] }>({ url: `/events/${id}/teams` }).then(
        (res) => res.data,
      )
      inFlight.set(id, pending)
      const settled = pending
      const forget = () => {
        if (inFlight.get(id) === settled) inFlight.delete(id)
      }
      settled.then(forget, forget)
    }
    return pending
  }

  async function load() {
    const id = toValue(eventId)
    const gen = ++generation
    if (!id) {
      teams.value = []
      loading.value = false
      error.value = null
      return
    }
    loading.value = true
    error.value = null
    try {
      const data = await fetchList(id)
      if (gen === generation) teams.value = data
    } catch (e) {
      if (gen === generation) {
        teams.value = []
        error.value = e
      }
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  watch([() => toValue(eventId), version], () => load(), { immediate: true })

  return { teams, loading, error, reload: load }
}

/**
 * Where a team is looked at and joined: the Teams page of its event, scrolled
 * to the team. Without an event id the page falls back to the selected event.
 */
export function teamsPageLocation(
  eventId: string | null | undefined,
  teamId?: string | null,
): RouteLocationRaw {
  const params = eventId ? { eventId } : {}
  const query = teamId ? { team: teamId } : {}
  return { name: 'teams', params, query }
}
