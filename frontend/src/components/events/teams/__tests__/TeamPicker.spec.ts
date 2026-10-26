// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RadioGroup } from '@/components/ui/radio-group'
import { Select } from '@/components/ui/select'

import TeamPicker from '@/components/events/teams/TeamPicker.vue'

import type { EventTeamRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "Who can book": the two modes, the team Select (driven through reka's
 * `update:modelValue`, like the location picker's spec) and the hints that
 * must not show while the list is still loading or failed.
 */

function team(id: string, name: string, extra: Partial<EventTeamRead> = {}): EventTeamRead {
  return {
    id,
    event_id: 'e1',
    name,
    requires_approval: true,
    created_at: '2026-10-01T00:00:00Z',
    member_count: 6,
    ...extra,
  }
}

const kasse = team('t-kasse', 'Kasse')
const kueche = team('t-kueche', 'Küche', { requires_approval: false, member_count: 9 })

const teams = ref<EventTeamRead[]>([kasse, kueche])
const loading = ref(false)
const error = ref<unknown>(null)
const reload = vi.fn()
const invalidateTeams = vi.fn()
const eventIds: unknown[] = []

vi.mock('@/composables/useTeams', () => ({
  useTeams: (id: () => string | null) => {
    eventIds.push(id())
    return { teams, loading, error, reload }
  },
  invalidateTeams: (...args: unknown[]) => invalidateTeams(...args),
  teamsPageLocation: (eventId: string) => ({
    name: 'teams',
    params: { eventId },
  }),
}))

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ hasRoute: () => true }),
}))

const canManage = vi.fn(() => true)
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canManageEvent: canManage }),
}))

beforeEach(() => {
  i18n.global.locale.value = 'en'
  teams.value = [kasse, kueche]
  loading.value = false
  error.value = null
  reload.mockReset()
  invalidateTeams.mockReset()
  canManage.mockReturnValue(true)
  eventIds.length = 0
})

const formStub = {
  name: 'TeamFormDialogStub',
  template: '<div data-stub="form" :data-open="open" />',
  props: ['open', 'eventId'],
  emits: ['saved', 'update:open'],
}

function mountPicker(props: Record<string, unknown> = {}) {
  return mount(TeamPicker, {
    props: { eventId: 'e1', modelValue: null, inputId: 'task-team', ...props },
    global: {
      plugins: [i18n],
      stubs: {
        RouterLink: RouterLinkStub,
        TeamFormDialog: formStub,
      },
    },
  })
}

type Wrapper = ReturnType<typeof mountPicker>

const setMode = async (w: Wrapper, mode: 'everyone' | 'team') => {
  w.findComponent(RadioGroup).vm.$emit('update:modelValue', mode)
  await nextTick()
}
const choose = async (w: Wrapper, value: string) => {
  w.findComponent(Select).vm.$emit('update:modelValue', value)
  await nextTick()
}
const lastModel = (w: Wrapper) => w.emitted('update:modelValue')?.at(-1)?.[0]
const has = (w: Wrapper, testid: string) => w.find(`[data-testid="${testid}"]`).exists()

describe('TeamPicker', () => {
  it('loads the teams of the event it is given', () => {
    mountPicker({ eventId: 'e7' })
    expect(eventIds).toEqual(['e7'])
  })

  it('starts on "everyone" without a team, and hides the team select', () => {
    const w = mountPicker()
    expect(w.findComponent(RadioGroup).props('modelValue')).toBe('everyone')
    expect(w.findComponent(Select).exists()).toBe(false)
  })

  it('starts on the task’s team', () => {
    const w = mountPicker({ modelValue: 't-kasse' })
    expect(w.findComponent(RadioGroup).props('modelValue')).toBe('team')
    expect(w.findComponent(Select).props('modelValue')).toBe('t-kasse')
    expect(w.find('[data-testid="task-team"]').attributes('id')).toBe('task-team')
  })

  it('follows a team filled in after mount', async () => {
    const w = mountPicker()
    await w.setProps({ modelValue: 't-kueche' })
    expect(w.findComponent(RadioGroup).props('modelValue')).toBe('team')
  })

  it('"only one team" with several teams waits for a choice', async () => {
    const w = mountPicker()
    await setMode(w, 'team')
    // Still null, so nothing to emit.
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect(w.findComponent(Select).props('modelValue')).toBe('__none')
    expect(has(w, 'team-picker-choose')).toBe(true)
  })

  it('"only one team" with a single team picks it', async () => {
    teams.value = [kasse]
    const w = mountPicker()
    await setMode(w, 'team')
    expect(lastModel(w)).toBe('t-kasse')
  })

  it('choosing a team sets the model, and "everyone" clears it', async () => {
    const w = mountPicker()
    await setMode(w, 'team')
    await choose(w, 't-kueche')
    expect(lastModel(w)).toBe('t-kueche')
    await w.setProps({ modelValue: 't-kueche' })

    await setMode(w, 'everyone')
    expect(lastModel(w)).toBeNull()

    // Back to "only one team": the team chosen before comes back.
    await setMode(w, 'team')
    expect(lastModel(w)).toBe('t-kueche')
  })

  it('"New team…" opens the form and keeps the current choice', async () => {
    const w = mountPicker({ modelValue: 't-kasse' })
    await choose(w, '__new')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect(w.find('[data-stub="form"]').attributes('data-open')).toBe('true')
  })

  it('selects a team the form hands back, and reloads the list', async () => {
    const w = mountPicker({ modelValue: null })
    await setMode(w, 'team')
    w.findComponent(formStub).vm.$emit('saved', team('t-new', 'Fahrdienst'))
    await nextTick()
    expect(lastModel(w)).toBe('t-new')
    expect(invalidateTeams).toHaveBeenCalledWith('e1')
  })

  it('selects the new team once the reloaded list has it', async () => {
    const w = mountPicker({ modelValue: null })
    await setMode(w, 'team')
    w.findComponent(formStub).vm.$emit('saved')
    await nextTick()
    teams.value = [kasse, kueche, team('t-new', 'Fahrdienst')]
    await nextTick()
    expect(lastModel(w)).toBe('t-new')
  })

  it('hides "New team…" without the right to manage the event', () => {
    canManage.mockReturnValue(false)
    const w = mountPicker()
    expect(w.find('[data-stub="form"]').exists()).toBe(false)
  })

  it('links to the Teams page when the event has no teams', async () => {
    teams.value = []
    const w = mountPicker()
    await setMode(w, 'team')
    expect(has(w, 'team-picker-no-teams')).toBe(true)
    expect(w.findComponent(RouterLinkStub).props('to')).toEqual({
      name: 'teams',
      params: { eventId: 'e1' },
    })
  })

  it('says nothing about "no teams" while the list is loading', async () => {
    teams.value = []
    loading.value = true
    const w = mountPicker()
    await setMode(w, 'team')
    expect(has(w, 'team-picker-no-teams')).toBe(false)
    expect(w.findComponent(Select).exists()).toBe(false)
  })

  it('shows a failed load with a retry, not as "no teams"', async () => {
    teams.value = []
    error.value = new Error('500')
    const w = mountPicker()
    await setMode(w, 'team')
    expect(has(w, 'team-picker-no-teams')).toBe(false)
    expect(has(w, 'team-picker-error')).toBe(true)
    await w.find('[data-testid="team-picker-error"] button').trigger('click')
    expect(reload).toHaveBeenCalled()
  })

  it('keeps an option for a team not in the list', () => {
    const w = mountPicker({ modelValue: 't-gone' })
    expect(w.findComponent(Select).props('modelValue')).toBe('t-gone')
  })

  it('is disabled without an event and asks for one', () => {
    const w = mountPicker({ eventId: null })
    expect(w.findComponent(RadioGroup).props('disabled')).toBe(true)
    expect(has(w, 'team-picker-no-event')).toBe(true)
  })

  it('forgets a team remembered from another event', async () => {
    const w = mountPicker({ modelValue: 't-kasse' })
    await setMode(w, 'everyone')
    await w.setProps({ eventId: 'e2', modelValue: null })
    const before = w.emitted('update:modelValue')!.length
    await setMode(w, 'team')
    expect(w.emitted('update:modelValue')!.slice(before).flat()).not.toContain('t-kasse')
  })
})
