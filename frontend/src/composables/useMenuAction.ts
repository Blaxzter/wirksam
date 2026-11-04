import { type InjectionKey, getCurrentInstance, inject, provide } from 'vue'

export interface MenuAction {
  /** From the item's `@select`: what to do once the menu has closed. */
  after: (action: () => void) => void
  /** `DropdownMenuContent`'s `@close-auto-focus`. */
  onCloseAutoFocus: (event: Event) => void
}

const MenuActionKey: InjectionKey<MenuAction> = Symbol('MenuAction')

/**
 * Run what a ⋯ menu item does only once the menu has closed and its button
 * has focus again. Meant for items that open a dialog.
 *
 * A dialog remembers whatever has focus when it opens and hands focus back to
 * it when it closes. Opened straight from a `DropdownMenuItem`, that is the
 * item, which is gone by then, so focus drops to `<body>` and a keyboard user
 * starts over at the top of the page. `await nextTick()` does not help: the
 * menu plays its exit animation first and focuses its button only after it.
 *
 * ```vue
 * const menu = useMenuAction()
 *
 * <DropdownMenuContent @close-auto-focus="menu.onCloseAutoFocus">
 *   <DropdownMenuItem @select="menu.after(() => (dialogOpen = true))">
 * ```
 *
 * One instance can serve every menu of a component, rows of a list included:
 * only one menu is open at a time, and each close takes the action with it.
 * An item that is a component of its own reaches it with `useMenuItemAction()`.
 */
export function useMenuAction(): MenuAction {
  let pending: (() => void) | null = null

  function after(action: () => void) {
    pending = action
  }

  function onCloseAutoFocus(event: Event) {
    const action = pending
    pending = null
    if (!action) return
    // Focus the button here rather than leave it to the menu, which would do
    // it a moment later, after the dialog has opened and looked for it.
    event.preventDefault()
    menuTrigger(event.target)?.focus()
    action()
  }

  const menu = { after, onCloseAutoFocus }
  if (getCurrentInstance()) provide(MenuActionKey, menu)
  return menu
}

/**
 * `after` of the menu this item sits in, for an item that is a component of
 * its own. Outside such a menu the action simply runs at once.
 */
export function useMenuItemAction(): MenuAction['after'] {
  return inject(MenuActionKey, null)?.after ?? ((action) => action())
}

/**
 * The button that opened a menu, from the menu's own element (or the wrapper
 * around it): reka labels the menu with its button's id.
 */
export function menuTrigger(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null
  const menu = target.matches('[role="menu"]') ? target : target.querySelector('[role="menu"]')
  const id = menu?.getAttribute('aria-labelledby')
  return id ? document.getElementById(id) : null
}
