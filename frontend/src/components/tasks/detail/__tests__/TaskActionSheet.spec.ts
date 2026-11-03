// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { Printer, Trash2 } from '@lucide/vue'
import { describe, expect, it } from 'vitest'

import TaskActionSheet from '@/components/tasks/detail/TaskActionSheet.vue'

import i18n from '@/locales/i18n'

/**
 * The phone action sheet of the task page: picking a row closes the sheet
 * and reports the row; "Cancel" only closes it.
 */

const passthrough = { template: '<div><slot /></div>' }

function mountSheet() {
  return mount(TaskActionSheet, {
    props: {
      open: true,
      title: 'Cafétheke',
      actions: [
        { key: 'print', label: 'Print', icon: Printer, testid: 'row-print' },
        {
          key: 'delete',
          label: 'Delete task',
          icon: Trash2,
          destructive: true,
          testid: 'row-delete',
        },
      ],
    },
    global: {
      plugins: [i18n],
      stubs: {
        Drawer: passthrough,
        DrawerContent: passthrough,
        DrawerHeader: passthrough,
        DrawerTitle: passthrough,
        DrawerDescription: passthrough,
      },
    },
  })
}

describe('TaskActionSheet', () => {
  it('closes and reports the row that was picked', async () => {
    const w = mountSheet()
    expect(w.text()).toContain('Cafétheke')
    await w.find('[data-testid="row-delete"]').trigger('click')
    expect(w.emitted('update:open')).toEqual([[false]])
    expect(w.emitted('select')).toEqual([['delete']])
  })

  it('marks a destructive row', () => {
    const w = mountSheet()
    expect(w.find('[data-testid="row-delete"]').classes()).toContain('text-destructive')
    expect(w.find('[data-testid="row-print"]').classes()).not.toContain('text-destructive')
  })

  it('closes without a choice on "Cancel"', async () => {
    i18n.global.locale.value = 'en'
    const w = mountSheet()
    const cancel = w.findAll('button').find((b) => b.text() === 'Cancel')!
    await cancel.trigger('click')
    expect(w.emitted('update:open')).toEqual([[false]])
    expect(w.emitted('select')).toBeUndefined()
  })
})
