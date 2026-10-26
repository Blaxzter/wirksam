// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'

import type { EventTeamRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Joining in place: an open team on the spot, a restricted one through the
 * shared request dialog (note and file slots), and a waiting request as such.
 */

const api = vi.hoisted(() => ({ post: vi.fn(), getAuthToken: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ post: api.post, getAuthToken: api.getAuthToken }),
}))

const upload = vi.hoisted(() => vi.fn())
vi.mock('@/components/events/teams/teamDocuments', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/events/teams/teamDocuments')>()),
  uploadTeamDocument: (...args: unknown[]) => upload(...args),
}))

const auth = vi.hoisted(() => ({
  profile: { is_sandbox: false } as { is_sandbox: boolean } | null,
  selectedEvent: null as { id: string; is_sandbox: boolean } | null,
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

const teams = ref<EventTeamRead[]>([])
const invalidateTeams = vi.fn()
vi.mock('@/composables/useTeams', () => ({
  useTeams: () => ({ teams, loading: ref(false), error: ref(null), reload: vi.fn() }),
  invalidateTeams: (...args: unknown[]) => invalidateTeams(...args),
}))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const toastApiError = vi.fn()
vi.mock('@/lib/api-errors', () => ({ toastApiError: (e: unknown) => toastApiError(e) }))

/** A file the dialog accepts: small and a PDF. */
const pdf = () => new File(['%PDF-1.4'], 'kurs.pdf', { type: 'application/pdf' })

const passthrough = { template: '<div><slot /></div>' }
const dialogStub = {
  props: ['open'],
  template: '<div v-if="open" data-stub="dialog"><slot /></div>',
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
  auth.profile = { is_sandbox: false }
  auth.selectedEvent = null
  teams.value = [
    {
      id: 't1',
      event_id: 'e1',
      name: 'Kasse',
      requires_approval: true,
      created_at: '2026-10-01T00:00:00Z',
      description: 'Cash desk at the entrance.',
      contact: 'Anna, 0151 1234567',
      lead_names: ['Anna'],
      requirements: [
        {
          id: 'r1',
          label: 'First-aid course',
          ask_issue_date: true,
          valid_for_years: 2,
          accepts_document: true,
        },
      ],
    },
  ]
})

function mountButton(props: Record<string, unknown> = {}) {
  return mount(TeamJoinButton, {
    props: { eventId: 'e1', teamId: 't1', teamName: 'Kasse', ...props },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: dialogStub,
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
      },
    },
  })
}

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('TeamJoinButton', () => {
  it('joins an open team on the spot', async () => {
    api.post.mockResolvedValue({ data: { status: 'approved' } })
    const w = mountButton({ requiresApproval: false })
    expect(w.text()).toContain('Join Kasse')

    await w.find('[data-testid="btn-team-join-t1"]').trigger('click')
    await flush()

    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/teams/t1/join',
      body: { message: null },
    })
    expect(w.emitted('joined')).toEqual([['approved']])
    expect(invalidateTeams).toHaveBeenCalledWith('e1')
    expect(toast.success).toHaveBeenCalled()
    // Joined: nothing left to offer.
    expect(w.find('[data-testid="btn-team-join-t1"]').exists()).toBe(false)
  })

  it('asks to join a restricted team with a note and a file', async () => {
    api.post.mockResolvedValue({ data: { status: 'pending' } })
    api.getAuthToken.mockResolvedValue('token')
    upload.mockResolvedValue(undefined)
    const w = mountButton()
    expect(w.text()).toContain('Ask to join Kasse')

    await w.find('[data-testid="btn-team-join-t1"]').trigger('click')
    const dialog = w.find('[data-stub="dialog"]')
    expect(dialog.text()).toContain('Cash desk at the entrance.')
    expect(dialog.text()).toContain('Anna, 0151 1234567')
    expect(dialog.text()).toContain('First-aid course')
    expect(dialog.text()).toContain('valid for 2 years')
    expect(dialog.text()).toContain('when Anna decides')

    // The same file slot as on the Teams page: nothing left to do elsewhere.
    const input = w.find('[data-testid="team-join-file-r1"] input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [pdf()] })
    await input.trigger('change')

    await w.find('[data-testid="team-join-note"]').setValue('  Did it last year.  ')
    await w.find('form').trigger('submit')
    await flush()

    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/teams/t1/join',
      body: { message: 'Did it last year.' },
    })
    expect(upload).toHaveBeenCalledWith('token', 'e1', 't1', 'r1', expect.any(File))
    expect(w.emitted('joined')).toEqual([['pending']])
    expect(invalidateTeams).toHaveBeenCalledWith('e1')
    expect(toast.success).toHaveBeenCalled()
    expect(w.find('[data-testid="btn-team-pending-t1"]').exists()).toBe(true)
  })

  it('offers no file slot in a demo', async () => {
    auth.profile = { is_sandbox: true }
    const w = mountButton()
    await w.find('[data-testid="btn-team-join-t1"]').trigger('click')
    expect(w.find('[data-testid="team-join-file-r1"]').exists()).toBe(false)
    expect(w.find('[data-stub="dialog"]').text()).toContain('cannot be attached in a demo')
  })

  it('shows a waiting request instead of asking again', () => {
    const w = mountButton({ myStatus: 'pending' })
    const pending = w.find('[data-testid="btn-team-pending-t1"]')
    expect(pending.exists()).toBe(true)
    expect(pending.attributes('disabled')).toBeDefined()
  })

  it('offers to ask again after a declined request', () => {
    const w = mountButton({ myStatus: 'declined' })
    expect(w.find('[data-testid="btn-team-join-t1"]').exists()).toBe(true)
  })

  it('keeps the button and reports a refused join', async () => {
    const failure = new Error('409')
    api.post.mockRejectedValue(failure)
    const w = mountButton({ requiresApproval: false })
    await w.find('[data-testid="btn-team-join-t1"]').trigger('click')
    await flush()

    expect(toastApiError).toHaveBeenCalledWith(failure)
    expect(w.emitted('joined')).toBeUndefined()
    expect(w.find('[data-testid="btn-team-join-t1"]').exists()).toBe(true)
  })
})
