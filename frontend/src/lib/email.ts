/**
 * Whether something typed into a search field looks like an e-mail address.
 *
 * Deliberately loose: it only decides whether a picker offers "Invite … by
 * e-mail". One `@` with something before it, a domain with a dot that neither
 * starts nor ends it, and no spaces. The server validates the address
 * properly and answers with a message when it disagrees.
 */
export function looksLikeEmail(text: string): boolean {
  const value = text.trim()
  if (!value || /\s/.test(value)) return false
  const at = value.indexOf('@')
  if (at <= 0 || at !== value.lastIndexOf('@')) return false
  const domain = value.slice(at + 1)
  const dot = domain.lastIndexOf('.')
  return dot > 0 && dot < domain.length - 1 && !domain.startsWith('.')
}

/**
 * The words of an address's local part that are worth matching a name on:
 * "jonas.weber@example.org" → ["jonas", "weber"].
 *
 * A picker uses them to list members who may be the same person under
 * another address. Parts shorter than three letters ("j", "jw") would match
 * nearly everyone, so they are left out.
 */
export function addressNameParts(email: string): string[] {
  const at = email.indexOf('@')
  const local = (at < 0 ? email : email.slice(0, at)).toLocaleLowerCase()
  return local.split(/[^\p{L}\p{N}]+/u).filter((part) => part.length >= 3)
}
