import { ref } from 'vue'

import { defineStore } from 'pinia'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import type { SidebarResponse } from '@/client/types.gen'

export const useSidebarStore = defineStore('sidebar', () => {
  const { get } = useAuthenticatedClient()

  const eventGroups = ref<SidebarResponse['event_groups']>([])
  const events = ref<SidebarResponse['events']>([])
  const bookings = ref<SidebarResponse['bookings']>([])
  const loaded = ref(false)

  async function fetch() {
    try {
      const res = await get<{ data: SidebarResponse }>({ url: '/dashboard/sidebar' })
      eventGroups.value = res.data.event_groups
      events.value = res.data.events
      bookings.value = res.data.bookings
      loaded.value = true
    } catch {
      // Sidebar is non-critical — fail silently
    }
  }

  return { eventGroups, events, bookings, loaded, fetch }
})
