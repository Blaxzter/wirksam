// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { ShiftBatchRead, TaskRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'
import TaskEditView from '@/views/tasks/TaskEditView.vue'

/**
 * What the task's own edit offers. With several batches the shifts belong to
 * the batches (each has its own edit on the task page), so the task's edit
 * offers just the details and saves them with a plain PATCH: it used to be
 * hidden on such a task, and the batch's edit has no name or description, so
 * an organiser could not rename the task at all.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))

const auth = vi.hoisted(() => ({ admin: true }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    profile: { id: 'me', time_format: 'h24' },
    canManageEvent: () => auth.admin,
  }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function task(overrides: Partial<TaskRead> = {}): TaskRead {
  return {
    id: 't1',
    event_id: 'e1',
    name: 'Bar',
    description: 'Drinks',
    location: 'Foyer',
    location_id: null,
    category: 'Catering',
    status: 'published',
    start_date: '2026-07-01',
    end_date: '2026-07-01',
    default_start_time: '10:00:00',
    default_end_time: '12:00:00',
    shift_duration_minutes: 60,
    people_per_shift: 1,
    schedule_overrides: [],
    can_manage: true,
    can_manage_shifts: true,
    ...overrides,
  } as TaskRead
}

function batch(id: string, date: string): ShiftBatchRead {
  return {
    id,
    task_id: 't1',
    start_date: date,
    end_date: date,
    default_start_time: '10:00:00',
    default_end_time: '12:00:00',
    shift_duration_minutes: 60,
    people_per_shift: 1,
    location: 'Foyer',
    category: null,
  } as ShiftBatchRead
}

let current: { task: TaskRead; batches: ShiftBatchRead[] }

beforeEach(() => {
  setActivePinia(createPinia())
  auth.admin = true
  api.get.mockReset()
  api.post.mockReset()
  api.patch.mockReset()
  api.get.mockImplementation(async ({ url }: { url: string }) => {
    if (url === '/tasks/t1') return { data: current.task }
    if (url === '/tasks/t1/batches') return { data: current.batches }
    if (url === '/events/e1') return { data: { id: 'e1', name: 'Fest' } }
    if (url === '/shifts/') return { data: { items: [] } }
    throw new Error(`unexpected GET ${url}`)
  })
  api.patch.mockImplementation(async () => ({ data: current.task }))
})

async function mountEdit(query: Record<string, string> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { name: 'tasks', path: '/app/tasks', component: { template: '<div />' } },
      { name: 'task-detail', path: '/app/tasks/:eventId', component: { template: '<div />' } },
      { name: 'task-edit', path: '/app/tasks/:eventId/edit', component: TaskEditView },
    ],
  })
  await router.push({ name: 'task-edit', params: { eventId: 't1' }, query })
  await router.isReady()
  const wrapper = mount(TaskEditView, {
    global: {
      plugins: [i18n, router],
      stubs: {
        DatePicker: true,
        LocationPicker: { props: ['inputId'], template: '<input :id="inputId" />' },
        TeamPicker: true,
        ScheduleConfigForm: true,
        ShiftPreviewGrid: true,
        ResponsiveDialog: true,
      },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('TaskEditView: the task with several batches', () => {
  beforeEach(() => {
    current = { task: task(), batches: [batch('b1', '2026-07-01'), batch('b2', '2026-07-03')] }
  })

  it('offers the name and description, and leaves the shifts to the batches', async () => {
    const { wrapper } = await mountEdit()

    expect(wrapper.find('[data-testid="input-task-name"]').exists()).toBe(true)
    expect(wrapper.find('#task-description').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-schedule"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="task-shifts-in-batches"]').text()).toContain('2 series')
    // The task's own place and category, which the task list and the
    // printout show; each series keeps its own for its shifts.
    expect(wrapper.find('#task-location').exists()).toBe(true)
    expect(wrapper.find('#task-category').exists()).toBe(true)
    expect(wrapper.find('[data-testid="task-place-in-list"]').exists()).toBe(true)
    // The team is the task's, so it is still offered to an organiser.
    expect(wrapper.find('[data-testid="section-who-can-book"]').exists()).toBe(true)
  })

  it('saves a rename with a plain PATCH and recreates no shifts', async () => {
    const { wrapper, router } = await mountEdit()

    await wrapper.find('[data-testid="input-task-name"]').setValue('Café')
    await wrapper.find('#task-category').setValue('Getränke')
    await wrapper.find('[data-testid="btn-submit"]').trigger('click')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(api.patch).toHaveBeenCalledTimes(1)
    expect(api.patch).toHaveBeenCalledWith({
      url: '/tasks/t1',
      body: {
        name: 'Café',
        description: 'Drinks',
        location_id: null,
        location: 'Foyer',
        category: 'Getränke',
      },
    })
    expect(router.currentRoute.value.name).toBe('task-detail')
  })

  it('still lets a batch be edited on its own', async () => {
    const { wrapper } = await mountEdit({ batchId: 'b2' })

    expect(wrapper.find('[data-testid="section-schedule"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="input-task-name"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="task-shifts-in-batches"]').exists()).toBe(false)
  })
})

describe('TaskEditView: a task with one batch', () => {
  beforeEach(() => {
    current = { task: task(), batches: [batch('b1', '2026-07-01')] }
  })

  it('edits the details and the shifts together', async () => {
    const { wrapper } = await mountEdit()

    expect(wrapper.find('[data-testid="input-task-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-schedule"]').exists()).toBe(true)
    expect(wrapper.find('#task-location').exists()).toBe(true)
    expect(wrapper.find('[data-testid="task-shifts-in-batches"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="task-place-in-list"]').exists()).toBe(false)
  })

  it('gives a person in charge of a locked voucher task the details only', async () => {
    auth.admin = false
    current.task = task({ can_manage_shifts: false, vouchers_per_shift: 2 })
    const { wrapper } = await mountEdit()

    expect(wrapper.find('[data-testid="task-voucher-shifts-locked"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-schedule"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="section-who-can-book"]').exists()).toBe(false)

    await wrapper.find('[data-testid="input-task-name"]').setValue('Café')
    await wrapper.find('[data-testid="btn-submit"]').trigger('click')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(api.patch).toHaveBeenCalledWith({
      url: '/tasks/t1',
      body: expect.objectContaining({ name: 'Café', location: 'Foyer', category: 'Catering' }),
    })
  })
})

describe('TaskEditView: a person in charge of a locked task with several batches', () => {
  beforeEach(() => {
    auth.admin = false
    current = {
      task: task({ can_manage_shifts: false, vouchers_per_shift: 2 }),
      batches: [batch('b1', '2026-07-01'), batch('b2', '2026-07-03')],
    }
  })

  it('still reaches the details, with the lock as the reason', async () => {
    const { wrapper, router } = await mountEdit()

    expect(router.currentRoute.value.name).toBe('task-edit')
    expect(wrapper.find('[data-testid="input-task-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="task-voucher-shifts-locked"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="task-shifts-in-batches"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="section-schedule"]').exists()).toBe(false)
  })

  it('still changes the place and category of the task, as before the second series', async () => {
    const { wrapper } = await mountEdit()

    expect(wrapper.find('#task-location').exists()).toBe(true)
    await wrapper.find('#task-category').setValue('Getränke')
    await wrapper.find('[data-testid="btn-submit"]').trigger('click')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(api.patch).toHaveBeenCalledWith({
      url: '/tasks/t1',
      body: expect.objectContaining({ location: 'Foyer', category: 'Getränke' }),
    })
  })

  it('is sent back from a batch, whose shifts are not theirs', async () => {
    const { router } = await mountEdit({ batchId: 'b1' })

    expect(router.currentRoute.value.name).toBe('task-detail')
  })
})
