import MarkdownIt from 'markdown-it'

/**
 * Markdown for text that event admins write and members read — today only
 * location descriptions.
 *
 * `html: false` is the safety story: raw HTML in the source is escaped, not
 * passed through, and markdown-it's own `validateLink` refuses `javascript:`,
 * `vbscript:`, `file:` and non-image `data:` URLs. That is why there is no
 * DOMPurify step — keep it that way rather than switching `html` on.
 *
 * The output is meant for `v-html`, and only through `LocationDescription.vue`,
 * so there is exactly one place where user-authored HTML reaches the DOM.
 */
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// No images: a description could otherwise make every reader's browser fetch
// a URL of the author's choosing. `![alt](url)` stays visible as plain text.
md.disable('image')

// Every link leaves the app: a new tab, no `window.opener`, and no ranking
// credit for whatever an admin chose to link. markdown-it ships no
// `link_open` rule of its own, so the default is plain `renderToken`.
md.renderer.rules.link_open = (tokens, idx, options, _env, self) => {
  const token = tokens[idx]!
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer nofollow')
  return self.renderToken(tokens, idx, options)
}

/** Render user-authored markdown to safe HTML. Empty input gives `''`. */
export function renderMarkdown(src: string | null | undefined): string {
  if (!src || !src.trim()) return ''
  return md.render(src)
}
