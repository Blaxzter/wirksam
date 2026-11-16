// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { computed, defineComponent, h } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NoticeDialog } from '@/composables/useSharedListPrint'

import { provideResponsiveDialogContext } from '@/components/ui/responsive-dialog/utils'

import SharedListPrintDialog from '@/components/shared-lists/SharedListPrintDialog.vue'

import i18n from '@/locales/i18n'

/**
 * Asked before a notice is printed with a new list: what the list will be and
 * which tasks go without a QR code, then create it or open the wizard. When
 * nothing can go on a list it says why and offers the plain sheet.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

/** The dialog shell, minus reka's portal. */
const ShellStub = defineComponent({
  props: { open: Boolean },
  emits: ['update:open'],
  setup(props, { slots, emit }) {
    provideResponsiveDialogContext({ isMobile: computed(() => false) })
    return () =>
      props.open
        ? h('div', [
            h('button', {
              'data-testid': 'shell-close',
              onClick: () => emit('update:open', false),
            }),
            slots.default?.(),
          ])
        : null
  },
})
const passthrough = { template: '<div><slot /></div>' }
const ContentStub = defineComponent({
  emits: ['closeAutoFocus'],
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})
const STUBS = {
  ResponsiveDialog: ShellStub,
  ResponsiveDialogContent: ContentStub,
  ResponsiveDialogHeader: passthrough,
  ResponsiveDialogTitle: passthrough,
  ResponsiveDialogDescription: passthrough,
  ResponsiveDialogBody: passthrough,
}

function mountDialog(dialog: NoticeDialog | null, busy = false, returnFocus?: () => void) {
  return mount(SharedListPrintDialog, {
    props: { dialog, busy, returnFocus },
    attachTo: document.body,
    global: { plugins: [i18n], stubs: STUBS },
  })
}

type Wrapper = ReturnType<typeof mountDialog>
const byTestId = (w: Wrapper, id: string) => w.find(`[data-testid="${id}"]`)

const create: NoticeDialog = {
  kind: 'create',
  eventId: 'e1',
  title: 'Kuchen',
  taskIds: ['t1'],
  leftOut: [],
  covering: false,
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SharedListPrintDialog', () => {
  it('is closed without a question', () => {
    expect(byTestId(mountDialog(null), 'shell-close').exists()).toBe(false)
  })

  it('says what the new list will be, in the wizard’s words', () => {
    const w = mountDialog(create)

    expect(w.text()).toContain("We'll make a shared list for the notice")
    expect(byTestId(w, 'shared-list-print-title').text()).toBe('Kuchen')
    expect(w.text()).toContain('all that are still to come')
    expect(byTestId(w, 'shared-list-setting-asked').text()).toBe('name and email')
    expect(byTestId(w, 'shared-list-setting-others').text()).toBe('only the free places')
    expect(byTestId(w, 'shared-list-setting-perPerson').text()).toBe('as many shifts as are free')
    expect(byTestId(w, 'shared-list-setting-open').text()).toBe('until the last shift starts')
    expect(byTestId(w, 'shared-list-print-left-out').exists()).toBe(false)
  })

  it('creates the list, or opens the wizard first', async () => {
    const w = mountDialog(create)

    await byTestId(w, 'shared-list-print-create').trigger('click')
    await byTestId(w, 'shared-list-print-customize').trigger('click')

    expect(w.emitted('create')).toHaveLength(1)
    expect(w.emitted('customize')).toHaveLength(1)
  })

  it('creates nothing twice while the list is on its way', async () => {
    const w = mountDialog(create, true)
    const button = byTestId(w, 'shared-list-print-create')

    expect(button.attributes('aria-disabled')).toBe('true')
    await button.trigger('click')
    expect(w.emitted('create')).toBeUndefined()
  })

  it('counts the tasks of one list for a whole event and names those left out', () => {
    const w = mountDialog({
      ...create,
      title: 'Basar – all tasks',
      taskIds: ['a', 'b'],
      leftOut: [
        { id: 'c', name: 'Bar', problem: 'team_locked' },
        { id: 'd', name: 'Kasse', problem: 'not_yours' },
        { id: 'e', name: 'Aufbau', problem: 'no_shift_ahead' },
      ],
      covering: true,
    })

    expect(w.text()).toContain('all that are still to come, from 2 tasks')
    const leftOut = byTestId(w, 'shared-list-print-left-out')
    expect(leftOut.text()).toContain('Printed without a QR code:')
    expect(leftOut.findAll('li').map((li) => li.text())).toEqual([
      '“Bar” is for one team only.',
      'Someone else is in charge of “Kasse”.',
      '“Aufbau” has no shift still to come.',
    ])
  })

  it('explains why a task gets no QR code and offers the plain sheet', async () => {
    const w = mountDialog({ kind: 'task', problem: 'no_free_place' })

    expect(w.text()).toContain('This sheet gets no QR code')
    expect(w.text()).toContain('No shift still to come has a free place.')
    expect(byTestId(w, 'shared-list-print-create').exists()).toBe(false)
    await byTestId(w, 'shared-list-print-plain').trigger('click')
    expect(w.emitted('plain')).toHaveLength(1)
  })

  it('explains a whole event that cannot go on one list', () => {
    const tooMany = mountDialog({ kind: 'event', reason: 'too_many', offered: 60, leftOut: [] })
    expect(tooMany.text()).toContain('The sheets get no QR code')
    expect(tooMany.text()).toContain('A shared list holds at most 50 tasks; this would be 60.')
    tooMany.unmount()

    const none = mountDialog({
      kind: 'event',
      reason: 'none_offered',
      offered: 0,
      leftOut: [{ id: 'a', name: 'Bar', problem: 'not_published' }],
    })
    expect(none.text()).toContain('No task can go on a shared list right now.')
    expect(byTestId(none, 'shared-list-print-left-out').text()).toContain("“Bar” isn't published.")
  })

  it('explains a whole event whose shifts are all full', () => {
    const w = mountDialog({ kind: 'event', reason: 'no_free_place', offered: 3, leftOut: [] })
    expect(w.text()).toContain('No shift still to come has a free place.')
  })

  it('hands focus to the page once closed, where no button opened it', () => {
    const returnFocus = vi.fn()
    const closed = () => new Event('focus', { cancelable: true })

    const own = mountDialog(create)
    const left = closed()
    own.findComponent(ContentStub).vm.$emit('closeAutoFocus', left)
    expect(left.defaultPrevented).toBe(false)
    own.unmount()

    const page = mountDialog(create, false, returnFocus)
    const handed = closed()
    page.findComponent(ContentStub).vm.$emit('closeAutoFocus', handed)
    expect(handed.defaultPrevented).toBe(true)
    expect(returnFocus).toHaveBeenCalledOnce()
  })

  it('closes on cancel and from the shell', async () => {
    const w = mountDialog({ kind: 'task', problem: 'team_locked' })

    await w
      .findAll('button')
      .find((b) => b.text() === 'Cancel')!
      .trigger('click')
    await byTestId(w, 'shell-close').trigger('click')

    expect(w.emitted('close')).toHaveLength(2)
  })
})
