// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { type LocationQueryRaw, RouterView, createMemoryHistory, createRouter } from 'vue-router'

import { useTaskFiltersStore } from '@/stores/eventFilters'

import TasksView from '@/views/tasks/TasksView.vue'

import i18n from '@/locales/i18n'

/**
 * The hide-full filter lives in the URL and nowhere else. The filter store
 * outlives the page, so the dashboard's "find a shift" link
 * (`?hide_full=true`) used to leave it on for the rest of the session: "Tasks"
 * in the navigation opened plain /tasks with full shifts still hidden.
 */

const api = vi.hoisted(() => ({
  get: vi.fn(),
  delete: vi.fn(),
}))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    selectedEventId: 'e1',
    selectedEvent: null,
    isManager: false,
    canManageEvent: () => false,
  }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

/** Like `PostAuthLayout`: a fresh `TasksView` for every full path. */
const Layout = {
  components: { RouterView },
  template: '<RouterView :key="$route.fullPath" />',
}

async function mountAt(query: LocationQueryRaw = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ name: 'tasks', path: '/app/tasks', component: TasksView }],
  })
  await router.push({ name: 'tasks', query })
  await router.isReady()
  mount(Layout, {
    global: {
      plugins: [i18n, router],
      stubs: {
        TaskQuickView: true,
        TaskListView: true,
        TaskCalendarView: true,
        TaskFilterMenu: true,
        ShiftDetailDialog: true,
        DeleteConfirmationDialog: true,
      },
    },
  })
  await flushPromises()
  return router
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  api.get.mockReset()
  api.get.mockResolvedValue({ data: { items: [] } })
})

describe('TasksView: the hide-full filter', () => {
  it('turns on from a "find a shift" link', async () => {
    const router = await mountAt({ hide_full: 'true' })

    expect(useTaskFiltersStore().hideFullShifts).toBe(true)
    expect(router.currentRoute.value.query.hide_full).toBe('true')
  })

  it('is off again when Tasks is opened from the navigation', async () => {
    const router = await mountAt({ hide_full: 'true' })

    await router.push({ name: 'tasks' })
    await flushPromises()

    expect(useTaskFiltersStore().hideFullShifts).toBe(false)
    expect(router.currentRoute.value.query).not.toHaveProperty('hide_full')
  })

  it('stays on across the remount that switching it on in the menu causes', async () => {
    const router = await mountAt()

    useTaskFiltersStore().hideFullShifts = true
    await flushPromises()

    expect(router.currentRoute.value.query.hide_full).toBe('true')
    expect(useTaskFiltersStore().hideFullShifts).toBe(true)
  })
})
