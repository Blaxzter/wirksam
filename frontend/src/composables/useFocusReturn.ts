export interface FocusReturn {
  /** `@open-auto-focus`: note who has focus, before anything moves it into the sheet. */
  remember: () => void
  /** `@close-auto-focus`, after the sheet's own handlers: give focus back. */
  restore: (event: Event) => void
}

/**
 * Hand focus back to whoever had it when a bottom sheet opened.
 *
 * A centred dialog does this by itself. reka's Drawer does not: on close it
 * focuses its `DrawerTrigger` and nothing else, and most of our sheets open
 * through `v-model` with no trigger at all (every `ResponsiveDialog` on a
 * phone, the task page's ⋯ sheet). Focus then dropped to `<body>`, and a
 * keyboard or switch user started over at the top of the page.
 *
 * Nothing is moved when focus has already gone somewhere else, such as into
 * a dialog that a row of the sheet opened, or when a handler of the sheet's
 * own decided where it goes (`event.defaultPrevented`). When the element is
 * gone, reka's own handling stays, which still finds a `DrawerTrigger`.
 */
export function useFocusReturn(): FocusReturn {
  let opener: HTMLElement | null = null

  function remember() {
    const active = document.activeElement
    opener = active instanceof HTMLElement && active !== document.body ? active : null
  }

  function restore(event: Event) {
    const target = opener
    opener = null
    if (event.defaultPrevented) return
    const sheet = event.target instanceof Node ? event.target : null
    const active = document.activeElement
    const lost = !active || active === document.body || !!sheet?.contains(active)
    if (!lost) {
      // Someone else has focus now: leave it there, and keep reka from
      // taking it to a trigger.
      event.preventDefault()
      return
    }
    if (!target?.isConnected) return
    event.preventDefault()
    target.focus({ preventScroll: true })
  }

  return { remember, restore }
}
