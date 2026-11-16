// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDialogStore } from '@/stores/dialog'

import GlobalDialog from '@/components/utils/GlobalDialog.vue'

import i18n from '@/locales/i18n'

/**
 * The app's one confirmation dialog hands focus back to the control that
 * opened it. When the confirmed action took that control away, the caller's
 * `focusInstead` decides where focus goes, rather than <body>.
 */

const passthrough = { template: '<div><slot /></div>' }
const Content = defineComponent({
  name: 'ResponsiveDialogContent',
  emits: ['closeAutoFocus'],
  template: '<div><slot /></div>',
})

function mountDialog() {
  return mount(GlobalDialog, {
    attachTo: document.body,
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: passthrough,
        ResponsiveDialogContent: Content,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogFooter: passthrough,
      },
    },
  })
}

/** A button that has focus, as the control that opens the dialog would. */
function opener(): HTMLButtonElement {
  const button = document.createElement('button')
  document.body.append(button)
  button.focus()
  return button
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('GlobalDialog', () => {
  it('lets the caller place focus once the control that opened it is gone', async () => {
    const wrapper = mountDialog()
    const focusInstead = vi.fn()
    const button = opener()
    void useDialogStore().confirm({ text: 'Take your name off?', focusInstead })
    await flushPromises()

    button.remove()
    const event = new Event('focus.autoFocusOnUnmount', { cancelable: true })
    wrapper.findComponent(Content).vm.$emit('closeAutoFocus', event)

    expect(focusInstead).toHaveBeenCalledOnce()
    expect(event.defaultPrevented).toBe(true)
  })

  it('leaves focus to go back to that control while it is still there', async () => {
    const wrapper = mountDialog()
    const focusInstead = vi.fn()
    opener()
    void useDialogStore().confirm({ text: 'Take your name off?', focusInstead })
    await flushPromises()

    const event = new Event('focus.autoFocusOnUnmount', { cancelable: true })
    wrapper.findComponent(Content).vm.$emit('closeAutoFocus', event)

    expect(focusInstead).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('changes nothing for a dialog that names no stand-in', async () => {
    const wrapper = mountDialog()
    const button = opener()
    void useDialogStore().confirm({ text: 'Sure?' })
    await flushPromises()

    button.remove()
    const event = new Event('focus.autoFocusOnUnmount', { cancelable: true })
    wrapper.findComponent(Content).vm.$emit('closeAutoFocus', event)

    expect(event.defaultPrevented).toBe(false)
  })
})
