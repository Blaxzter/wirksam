/**
 * The first checkbox in `root` that can be ticked: a table's header box, or
 * the first row's. Where a table's own controls send focus back to once
 * something that held it has gone.
 */
export function firstCheckbox(root: Element | null | undefined): HTMLElement | null {
  return root?.querySelector<HTMLElement>('[role="checkbox"]:not([disabled])') ?? null
}
