// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { describe, expect, it, vi } from 'vitest'

import TeamFormDialog from '@/components/events/teams/TeamFormDialog.vue'

import type { EventTeamRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Saving a team with approval switched off lets everyone waiting in and deletes
 * their files, so the form says so first.
 */

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ post: vi.fn(), patch: vi.fn() }),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const passthrough = { template: '<div><slot /></div>' }

function team(overrides: Partial<EventTeamRead> = {}): EventTeamRead {
  return {
    id: 't1',
    event_id: 'e1',
    name: 'Cash desk',
    requires_approval: true,
    pending_count: 2,
    requirements: [],
    ...overrides,
  } as EventTeamRead
}

async function mountForm(editing: EventTeamRead | null) {
  const w = mount(TeamFormDialog, {
    props: { eventId: 'e1', team: editing, open: false },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: passthrough,
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
      },
    },
  })
  await w.setProps({ open: true })
  await flushPromises()
  return w
}

const warning = '[data-testid="team-approval-off-warning"]'

async function switchApprovalOff(w: Awaited<ReturnType<typeof mountForm>>) {
  await w.get('[data-testid="team-requires-approval"]').trigger('click')
  await flushPromises()
}

describe('TeamFormDialog', () => {
  it('stays quiet until approval is switched off', async () => {
    const w = await mountForm(team())
    expect(w.find(warning).exists()).toBe(false)
  })

  it('says how many people get in and that their files go', async () => {
    const w = await mountForm(team())
    await switchApprovalOff(w)
    expect(w.get(warning).text()).toContain('2 people')
    expect(w.get(warning).text()).toContain('deleted')
  })

  it('takes the singular for one person', async () => {
    const w = await mountForm(team({ pending_count: 1 }))
    await switchApprovalOff(w)
    expect(w.get(warning).text()).toContain('The person waiting')
  })

  it('has nothing to say when nobody is waiting', async () => {
    const w = await mountForm(team({ pending_count: 0 }))
    await switchApprovalOff(w)
    expect(w.find(warning).exists()).toBe(false)
  })

  it('has nothing to say for a team that was open already, or a new one', async () => {
    const open = await mountForm(team({ requires_approval: false }))
    expect(open.find(warning).exists()).toBe(false)

    const fresh = await mountForm(null)
    await switchApprovalOff(fresh)
    expect(fresh.find(warning).exists()).toBe(false)
  })
})
