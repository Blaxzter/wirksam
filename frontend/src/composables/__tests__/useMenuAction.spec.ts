// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

import { afterEach, describe, expect, it, vi } from 'vitest'

import { menuTrigger, useMenuAction, useMenuItemAction } from '@/composables/useMenuAction'

/**
 * A dialog opened from a ⋯ item has to find the menu's button focused, or it
 * hands focus back to nothing when it closes. These tests pin the order: the
 * action waits for the menu's `close-auto-focus`, focuses the button the menu
 * names in `aria-labelledby`, and only then runs.
 */

/** A closed menu as reka leaves it: the button, and the menu labelled by it. */
function renderMenu() {
  document.body.innerHTML = `
    <button id="trigger">⋯</button>
    <div data-reka-popper-content-wrapper>
      <div role="menu" aria-labelledby="trigger"></div>
    </div>
    <button id="elsewhere">elsewhere</button>
  `
  return {
    trigger: document.getElementById('trigger') as HTMLButtonElement,
    menu: document.querySelector('[role="menu"]') as HTMLElement,
    wrapper: document.querySelector('[data-reka-popper-content-wrapper]') as HTMLElement,
  }
}

const closeEvent = (target: HTMLElement) => {
  const event = new CustomEvent('focusScope.autoFocusOnUnmount', { cancelable: true })
  target.dispatchEvent(event)
  return event
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useMenuAction', () => {
  it('runs the queued action on close, after focusing the menu button', () => {
    const { trigger, menu } = renderMenu()
    const { after, onCloseAutoFocus } = useMenuAction()
    let focusedWhenRun: Element | null = null
    const action = vi.fn(() => {
      focusedWhenRun = document.activeElement
    })

    after(action)
    expect(action).not.toHaveBeenCalled()

    const event = closeEvent(menu)
    onCloseAutoFocus(event)

    expect(action).toHaveBeenCalledOnce()
    expect(focusedWhenRun).toBe(trigger)
    // The menu must not move focus again after the dialog has opened.
    expect(event.defaultPrevented).toBe(true)
  })

  it('leaves a close without a queued action to the menu', () => {
    const { menu } = renderMenu()
    document.getElementById('elsewhere')!.focus()
    const { onCloseAutoFocus } = useMenuAction()

    const event = closeEvent(menu)
    onCloseAutoFocus(event)

    expect(event.defaultPrevented).toBe(false)
    expect(document.activeElement?.id).toBe('elsewhere')
  })

  it('runs an action once, not again on the next close', () => {
    const { menu } = renderMenu()
    const { after, onCloseAutoFocus } = useMenuAction()
    const action = vi.fn()

    after(action)
    onCloseAutoFocus(closeEvent(menu))
    onCloseAutoFocus(closeEvent(menu))

    expect(action).toHaveBeenCalledOnce()
  })

  it('still runs the action when the button cannot be found', () => {
    const { after, onCloseAutoFocus } = useMenuAction()
    const action = vi.fn()

    after(action)
    onCloseAutoFocus(new Event('close'))

    expect(action).toHaveBeenCalledOnce()
  })
})

describe('menuTrigger', () => {
  it('finds the button from the menu itself or the wrapper around it', () => {
    const { trigger, menu, wrapper } = renderMenu()

    expect(menuTrigger(menu)).toBe(trigger)
    expect(menuTrigger(wrapper)).toBe(trigger)
  })

  it('gives up on anything that is not a labelled menu', () => {
    document.body.innerHTML = '<div role="menu"></div><p id="text"></p>'

    expect(menuTrigger(null)).toBeNull()
    expect(menuTrigger(document.querySelector('[role="menu"]'))).toBeNull()
    expect(menuTrigger(document.getElementById('text'))).toBeNull()
  })
})

describe('useMenuItemAction', () => {
  it("queues on the surrounding menu's instance", () => {
    renderMenu()
    const action = vi.fn()
    let parent: ReturnType<typeof useMenuAction> | undefined

    const Item = defineComponent({
      setup() {
        const afterMenu = useMenuItemAction()
        return () => h('button', { onClick: () => afterMenu(action) })
      },
    })
    const Menu = defineComponent({
      setup() {
        parent = useMenuAction()
        return () => h(Item)
      },
    })

    const wrapper = mount(Menu)
    void wrapper.find('button').trigger('click')
    expect(action).not.toHaveBeenCalled()

    parent!.onCloseAutoFocus(closeEvent(document.querySelector('[role="menu"]')!))
    expect(action).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('runs at once outside a menu', () => {
    const action = vi.fn()
    let afterMenu: ReturnType<typeof useMenuItemAction> | undefined

    mount(
      defineComponent({
        setup() {
          afterMenu = useMenuItemAction()
          return () => h('span')
        },
      }),
    ).unmount()
    afterMenu!(action)

    expect(action).toHaveBeenCalledOnce()
  })
})
