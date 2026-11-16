// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListWizardApi } from '@/composables/useSharedListWizardApi'

import type {
  EventRead,
  SharedListCandidate,
  SharedListCandidateShift,
  SharedListDetail,
} from '@/client/types.gen'
import i18n from '@/locales/i18n'
import SharedListWizardView from '@/views/shared-lists/SharedListWizardView.vue'

/**
 * The wizard's own behaviour: a step opens only once the one before it is
 * fine, a blocker shows only after a change or a press of Next, focus lands
 * on the new step's heading, nothing unsaved is lost without asking, an edit
 * sends only what changed and says when the names setting changes.
 */

const fixtures = vi.hoisted(() => ({
  shifts: [] as SharedListCandidateShift[],
  candidates: [] as SharedListCandidate[],
  leaveGuard: null as null | (() => Promise<boolean> | boolean),
}))
const route = vi.hoisted(() => ({
  name: 'shared-list-create',
  params: { eventId: 'e1' } as Record<string, string>,
  query: {} as Record<string, string>,
}))
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
const dialog = vi.hoisted(() => ({ confirm: vi.fn() }))
const toasts = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}))
const breadcrumbs = vi.hoisted(() => ({ setBreadcrumbs: vi.fn() }))

vi.mock('@/composables/useSharedListWizardApi', async () => {
  const { computed, shallowRef } = await import('vue')
  const byTask = shallowRef(new Map<string, SharedListCandidateShift[]>())
  const fake = {
    fetchEvent: vi.fn(),
    fetchCandidates: vi.fn(),
    findCandidates: vi.fn(),
    fetchCandidateShifts: vi.fn(),
    fetchDetail: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    shiftsByTask: computed(() => byTask.value),
    shiftsLoading: computed(() => false),
    shiftsError: computed(() => null),
    loadShifts: vi.fn(async (_eventId: string, ids: readonly string[]) => {
      const next = new Map(byTask.value)
      for (const id of ids)
        next.set(
          id,
          fixtures.shifts.filter((s) => s.task_id === id),
        )
      byTask.value = next
    }),
    forget: () => (byTask.value = new Map()),
  }
  return { useSharedListWizardApi: () => fake }
})
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => route,
  useRouter: () => router,
  onBeforeRouteLeave: (guard: () => Promise<boolean> | boolean) => {
    fixtures.leaveGuard = guard
  },
}))
vi.mock('vue-sonner', () => ({ toast: toasts }))
vi.mock('@/composables/useDialog', () => ({ useDialog: () => dialog }))
vi.mock('@/stores/breadcrumb', () => ({ useBreadcrumbStore: () => breadcrumbs }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))
vi.mock('@/lib/api-errors', () => ({
  toastApiError: vi.fn(),
  getApiErrorMessage: () => 'failed',
}))

type FakeApi = ReturnType<typeof useSharedListWizardApi> & { forget: () => void }
const api = useSharedListWizardApi() as FakeApi

const DAY = '2099-12-05'
const NEXT_DAY = '2099-12-06'
const NO_FREE_PLACE = 'Every shift you chose is full. Nobody could sign up through the link.'

function shift(id: string, taskId: string, date: string, free = 2): SharedListCandidateShift {
  return {
    id,
    task_id: taskId,
    date,
    start_time: '10:00:00',
    end_time: '12:00:00',
    capacity: 2,
    free,
  }
}

function candidate(id: string, name: string): SharedListCandidate {
  return {
    id,
    name,
    location: null,
    manager_names: [],
    shift_count: 2,
    dates: [DAY, NEXT_DAY],
    capacity: 4,
    free: 4,
    team: null,
    earns_vouchers: false,
  }
}

const EVENT = {
  id: 'e1',
  name: 'Fair',
  start_date: DAY,
  end_date: NEXT_DAY,
  status: 'published',
  timezone: 'Europe/Berlin',
  is_sandbox: false,
  can_manage: true,
  managed_task_count: 0,
  managers_share_lists: true,
  is_expired: false,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
} satisfies EventRead

function detail(overrides: Partial<SharedListDetail> = {}): SharedListDetail {
  return {
    id: 'l1',
    code: 'code1',
    title: 'Kitchen: who can help?',
    share_note: null,
    status: 'live',
    effective_status: 'live',
    ends_mode: 'last_shift',
    ends_on: null,
    closes_at: null,
    expires_soon: false,
    is_full: false,
    created_at: '2026-11-01T10:00:00',
    created_by_name: 'Anna',
    tasks: [{ id: 'kitchen', name: 'Kitchen' }],
    only_days: null,
    excluded_shift_ids: ['k2', 'started'],
    excluded_shift_count: 2,
    capacity: 4,
    free: 4,
    signup_count: 0,
    guest_count: 0,
    view_count: 0,
    issue: null,
    access: 'admin',
    intro: null,
    ask_email: 'required',
    ask_phone: 'off',
    show_names: 'first',
    max_per_person: null,
    rotated_at: null,
    paused_at: null,
    ended_at: null,
    task_ids: ['kitchen'],
    detail_tasks: [
      {
        id: 'kitchen',
        name: 'Kitchen',
        offered: true,
        not_offered_reason: null,
        shift_count: 1,
        capacity: 2,
        free: 2,
        only_days: null,
      },
    ],
    event: {
      id: 'e1',
      name: 'Fair',
      start_date: DAY,
      end_date: NEXT_DAY,
      timezone: 'Europe/Berlin',
    },
    ...overrides,
  }
}

const mounted: ReturnType<typeof mount>[] = []

async function open() {
  const wrapper = mount(SharedListWizardView, {
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

const byTestId = (wrapper: ReturnType<typeof mount>, id: string) =>
  wrapper.find(`[data-testid="${id}"]`)

beforeEach(() => {
  vi.clearAllMocks()
  api.forget()
  i18n.global.locale.value = 'en'
  route.name = 'shared-list-create'
  route.params = { eventId: 'e1' }
  route.query = {}
  fixtures.leaveGuard = null
  fixtures.shifts = [
    shift('k1', 'kitchen', DAY),
    shift('k2', 'kitchen', NEXT_DAY),
    shift('b1', 'bar', DAY),
  ]
  fixtures.candidates = [candidate('kitchen', 'Kitchen'), candidate('bar', 'Bar')]
  vi.mocked(api.fetchEvent).mockResolvedValue(EVENT)
  vi.mocked(api.fetchCandidates).mockImplementation(async () => ({
    items: fixtures.candidates,
    total: fixtures.candidates.length,
    skip: 0,
    limit: 50,
    locked_count: 0,
    locked_names: [],
  }))
  vi.mocked(api.findCandidates).mockImplementation(async (_eventId, ids) =>
    fixtures.candidates.filter((c) => ids.includes(c.id)),
  )
})

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('creating a list', () => {
  it('opens on the tasks step without greeting anyone with an error', async () => {
    const wrapper = await open()
    expect(byTestId(wrapper, 'page-heading').text()).toBe('Share a list')
    expect(byTestId(wrapper, 'wizard-step-position').text()).toBe('Step 1 of 3')
    expect(byTestId(wrapper, 'wizard-step-blocked').exists()).toBe(false)
    expect(byTestId(wrapper, 'btn-step-next').attributes('aria-disabled')).toBe('true')
  })

  it('says what is missing when Next is pressed too early, and stays put', async () => {
    const wrapper = await open()
    await byTestId(wrapper, 'btn-step-next').trigger('click')

    expect(byTestId(wrapper, 'wizard-step-blocked').text()).toBe('Choose at least one task.')
    expect(byTestId(wrapper, 'btn-step-next').attributes('aria-describedby')).toBe(
      'wizard-step-blocked',
    )
    expect(byTestId(wrapper, 'wizard-step-position').text()).toBe('Step 1 of 3')
  })

  it('follows the tasks with the title and moves on with focus on the next heading', async () => {
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()

    expect(api.loadShifts).toHaveBeenLastCalledWith('e1', ['kitchen'])
    expect(byTestId(wrapper, 'wizard-summary').text()).toContain('2 shifts')
    expect(byTestId(wrapper, 'btn-step-next').attributes('aria-disabled')).toBe('false')

    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()

    expect(byTestId(wrapper, 'wizard-step-position').text()).toBe('Step 2 of 3')
    expect(document.activeElement?.getAttribute('data-testid')).toBe('wizard-step-heading')
    expect((byTestId(wrapper, 'wizard-title').element as HTMLInputElement).value).toBe(
      'Kitchen: who can help?',
    )
  })

  it('asks for a day or shift once every day is left out', async () => {
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()
    await byTestId(wrapper, `wizard-day-check-${DAY}`).trigger('click')
    await byTestId(wrapper, `wizard-day-check-${NEXT_DAY}`).trigger('click')

    expect(byTestId(wrapper, `wizard-day-${DAY}`).attributes('data-state')).toBe('unchecked')
    expect(byTestId(wrapper, 'wizard-step-blocked').text()).toBe(
      'Choose at least one day or shift.',
    )
  })

  it('keeps the limit per person chosen when the only task is swapped for another', async () => {
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'wizard-max-per').setValue('1')
    await byTestId(wrapper, 'btn-step-back').trigger('click')
    await flushPromises()

    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'wizard-task-check-bar').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()

    expect((byTestId(wrapper, 'wizard-max-per').element as HTMLSelectElement).value).toBe('1')
  })

  it('says which days, without a doubled full stop after a German date', async () => {
    i18n.global.locale.value = 'de'
    fixtures.shifts.push(shift('k3', 'kitchen', '2099-12-08'))
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()
    await byTestId(wrapper, `wizard-day-check-${NEXT_DAY}`).trigger('click')

    const summary = byTestId(wrapper, 'wizard-summary').text()
    expect(summary).toContain('Nur an diesen Tagen: Sa., 5.12. und Di., 8.12.')
    expect(summary).not.toContain('..')
  })

  it('sets no limit per person unless asked, then opens the list and offers to share it', async () => {
    vi.mocked(api.create).mockResolvedValue(detail({ id: 'new', code: 'fresh' }))
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()

    const maxPer = byTestId(wrapper, 'wizard-max-per')
    expect((maxPer.element as HTMLSelectElement).value).toBe('')
    expect(maxPer.find('option:checked').text()).toBe('as many as are free')

    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()

    expect(api.create).toHaveBeenCalledWith('e1', {
      title: 'Kitchen: who can help?',
      intro: null,
      share_note: null,
      task_ids: ['kitchen'],
      excluded_shift_ids: [],
      ask_email: 'required',
      ask_phone: 'off',
      show_names: 'none',
      max_per_person: null,
      ends_mode: 'last_shift',
      ends_on: null,
    })
    expect(byTestId(wrapper, 'wizard-step-position').text()).toBe('Step 3 of 3')
    expect((byTestId(wrapper, 'wizard-share-link').element as HTMLInputElement).value).toMatch(
      /\/l\/fresh$/,
    )
    const text = (byTestId(wrapper, 'wizard-share-message').element as HTMLTextAreaElement).value
    expect(text).toContain('“Fair”')
    expect(text).toContain('Kitchen')
    expect(text).toMatch(/\/l\/fresh$/)

    // From here on each way out takes the wizard's place in the history: Back
    // must not open it empty, ready to share the same tasks again.
    router.push.mockClear()
    await byTestId(wrapper, 'btn-preview').trigger('click')
    expect(router.replace).toHaveBeenLastCalledWith({
      name: 'shared-lists',
      params: { eventId: 'e1' },
      query: { tab: 'preview', preview: 'new' },
    })
    await byTestId(wrapper, 'wizard-print-notice').trigger('click')
    expect(router.replace).toHaveBeenLastCalledWith({
      name: 'print-list',
      params: { listId: 'new' },
    })
    await byTestId(wrapper, 'btn-done').trigger('click')
    expect(router.replace).toHaveBeenLastCalledWith({
      name: 'shared-lists',
      params: { eventId: 'e1' },
      query: {},
    })
    expect(router.push).not.toHaveBeenCalled()
  })

  it('starts with the tasks picked on the tasks tab, titled after them', async () => {
    route.query = { tasks: 'bar,nope,bar' }
    const wrapper = await open()

    expect(api.findCandidates).toHaveBeenCalledWith('e1', ['bar', 'nope'])
    expect(byTestId(wrapper, 'wizard-picked-bar').exists()).toBe(true)
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    expect((byTestId(wrapper, 'wizard-title').element as HTMLInputElement).value).toBe(
      'Bar: who can help?',
    )
  })

  it('copies another list as a new one, its title as typed', async () => {
    route.query = { from: 'old' }
    vi.mocked(api.fetchDetail).mockResolvedValue(
      detail({ id: 'old', status: 'ended', title: 'Christmas' }),
    )
    const wrapper = await open()

    expect(api.fetchDetail).toHaveBeenCalledWith('old')
    expect(byTestId(wrapper, 'page-heading').text()).toBe('Share a list')
    expect(byTestId(wrapper, 'wizard-step-position').text()).toBe('Step 1 of 3')
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    expect((byTestId(wrapper, 'wizard-title').element as HTMLInputElement).value).toBe('Christmas')
  })

  it('sends someone who may not share lists home', async () => {
    vi.mocked(api.fetchEvent).mockResolvedValue({ ...EVENT, can_manage: false })
    await open()
    expect(toasts.error).toHaveBeenCalledWith('You cannot share lists for this event.')
    expect(router.replace).toHaveBeenCalledWith({ name: 'home' })
  })
})

describe('leaving', () => {
  it('lets someone go who changed nothing', async () => {
    await open()
    expect(await fixtures.leaveGuard?.()).toBe(true)
    expect(dialog.confirm).not.toHaveBeenCalled()
  })

  it('asks before throwing away a change, and keeps it on no', async () => {
    dialog.confirm.mockResolvedValue(false)
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()

    expect(await fixtures.leaveGuard?.()).toBe(false)
    expect(dialog.confirm).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Discard your changes?', variant: 'destructive' }),
    )
  })

  it('does not ask once the list is open', async () => {
    vi.mocked(api.create).mockResolvedValue(detail({ id: 'new' }))
    const wrapper = await open()
    await byTestId(wrapper, 'wizard-task-check-kitchen').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()

    expect(await fixtures.leaveGuard?.()).toBe(true)
  })
})

describe('editing a list', () => {
  beforeEach(() => {
    route.name = 'shared-list-edit'
    route.params = { eventId: 'e1', listId: 'l1' }
  })

  it('has two steps, both open, and loads the list with its exclusions', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(detail())
    const wrapper = await open()

    expect(byTestId(wrapper, 'page-heading').text()).toBe('Edit list')
    expect(byTestId(wrapper, 'wizard-step-position').text()).toBe('Step 1 of 2')
    expect(byTestId(wrapper, `wizard-day-${NEXT_DAY}`).attributes('data-state')).toBe('unchecked')
    expect(byTestId(wrapper, 'step-settings').attributes('disabled')).toBeUndefined()
  })

  it('says a change of the names setting is for new sign-ups, and saves only that', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(detail())
    vi.mocked(api.update).mockResolvedValue(detail({ show_names: 'none' }))
    const wrapper = await open()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()

    expect(byTestId(wrapper, 'wizard-show-names-changed').exists()).toBe(false)
    await byTestId(wrapper, 'wizard-show-names-none').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'wizard-show-names-changed').text()).toContain(
      'everyone who signs up from now on',
    )

    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()

    expect(api.update).toHaveBeenCalledWith('l1', { show_names: 'none' })
    expect(toasts.success).toHaveBeenCalledWith('Saved. The link stays the same.')
    expect(router.push).toHaveBeenCalledWith({
      name: 'shared-lists',
      params: { eventId: 'e1' },
      query: { list: 'l1' },
    })
    expect(await fixtures.leaveGuard?.()).toBe(true)
  })

  it('lets a list that closed on a past day have its text corrected, as the API does', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(
      detail({ ends_mode: 'date', ends_on: '2020-01-01' }),
    )
    vi.mocked(api.update).mockResolvedValue(detail())
    const wrapper = await open()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'wizard-title').setValue('Kitchen, again')

    expect(byTestId(wrapper, 'wizard-step-blocked').exists()).toBe(false)
    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('l1', { title: 'Kitchen, again' })
  })

  it('wants a closing day ahead once the selection changes', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(
      detail({ ends_mode: 'date', ends_on: '2020-01-01' }),
    )
    const wrapper = await open()
    await byTestId(wrapper, `wizard-day-check-${NEXT_DAY}`).trigger('click')
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()

    expect(byTestId(wrapper, 'wizard-step-blocked').text()).toBe('That day is already over.')
    await byTestId(wrapper, 'btn-submit').trigger('click')
    expect(api.update).not.toHaveBeenCalled()
  })

  const withTent = () =>
    detail({
      task_ids: ['kitchen', 'tent'],
      detail_tasks: [
        ...detail().detail_tasks,
        {
          id: 'tent',
          name: 'Tent',
          offered: false,
          not_offered_reason: 'team_locked',
          shift_count: 0,
          capacity: 0,
          free: 0,
          only_days: null,
        },
      ],
    })

  it('names a task the list can no longer offer once the tasks change', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(withTent())
    const wrapper = await open()
    expect(api.loadShifts).toHaveBeenCalledWith('e1', ['kitchen'])

    await byTestId(wrapper, 'wizard-task-check-bar').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    expect(byTestId(wrapper, 'wizard-step-blocked').text()).toContain('“Tent” is only for a team')
    expect(byTestId(wrapper, 'step-settings').attributes('disabled')).toBeDefined()
  })

  it('lets a list keep a task it can no longer offer while its text is changed', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(withTent())
    vi.mocked(api.update).mockResolvedValue(detail())
    const wrapper = await open()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'wizard-title').setValue('Kitchen and tent')
    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()

    expect(api.update).toHaveBeenCalledWith('l1', { title: 'Kitchen and tent' })
  })

  it('lets a full list have its text changed, as the API does', async () => {
    fixtures.shifts = [shift('k1', 'kitchen', DAY, 0), shift('k2', 'kitchen', NEXT_DAY, 0)]
    vi.mocked(api.fetchDetail).mockResolvedValue(detail())
    vi.mocked(api.update).mockResolvedValue(detail())
    const wrapper = await open()
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'wizard-intro').setValue("We're full, thanks")
    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()

    expect(api.update).toHaveBeenCalledWith('l1', { intro: "We're full, thanks" })
  })

  it('still wants a free place once the selection of a full list changes', async () => {
    fixtures.shifts = [shift('k1', 'kitchen', DAY, 0), shift('k2', 'kitchen', NEXT_DAY, 0)]
    vi.mocked(api.fetchDetail).mockResolvedValue(detail())
    const wrapper = await open()
    await byTestId(wrapper, `wizard-day-check-${NEXT_DAY}`).trigger('click')
    await byTestId(wrapper, 'btn-step-next').trigger('click')

    expect(byTestId(wrapper, 'wizard-step-blocked').text()).toBe(NO_FREE_PLACE)
    expect(byTestId(wrapper, 'step-settings').attributes('disabled')).toBeDefined()
  })

  it('leaves a limit per person alone that is above the shifts still ahead', async () => {
    fixtures.shifts = [shift('k1', 'kitchen', DAY)]
    vi.mocked(api.fetchDetail).mockResolvedValue(
      detail({ max_per_person: 2, excluded_shift_ids: [] }),
    )
    vi.mocked(api.update).mockResolvedValue(detail())
    const wrapper = await open()

    // Nothing changed by opening it, so leaving asks nothing.
    expect(await fixtures.leaveGuard?.()).toBe(true)
    await byTestId(wrapper, 'btn-step-next').trigger('click')
    await flushPromises()
    expect((byTestId(wrapper, 'wizard-max-per').element as HTMLSelectElement).value).toBe('2')

    await byTestId(wrapper, 'wizard-title').setValue('Kitchen, typo fixed')
    await byTestId(wrapper, 'btn-submit').trigger('click')
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('l1', { title: 'Kitchen, typo fixed' })
  })

  it('refuses an ended list and shows it instead', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(detail({ status: 'ended' }))
    await open()
    expect(toasts.error).toHaveBeenCalledWith(
      'This list has ended and cannot be changed any more. You can share it again.',
    )
    expect(router.replace).toHaveBeenCalledWith({
      name: 'shared-lists',
      params: { eventId: 'e1' },
      query: { list: 'l1' },
    })
    expect(api.fetchEvent).not.toHaveBeenCalled()
  })

  it('refuses someone who may only look at the list', async () => {
    vi.mocked(api.fetchDetail).mockResolvedValue(detail({ access: 'viewer' }))
    await open()
    expect(toasts.error).toHaveBeenCalledWith('You can only look at this list, not edit it.')
  })
})
