/**
 * Where the project lives upstream. Every deployment links back to the same
 * repository, so this is a build-time constant rather than runtime config.
 */
export const REPO_URL = 'https://github.com/Blaxzter/wirksam'

/** Where feedback goes from people without a GitHub account. */
export const FEEDBACK_EMAIL = 'mail@fabraham.dev'

/** The issue forms in `.github/ISSUE_TEMPLATE/`, by file name. */
export type IssueTemplate = 'feature_request.yml' | 'bug_report.yml'

/**
 * Opens the chosen issue form directly. GitHub asks for a sign-in first; there
 * is no anonymous way to file an issue.
 */
export function newIssueUrl(template: IssueTemplate): string {
  return `${REPO_URL}/issues/new?template=${template}`
}

/** A `mailto:` link to {@link FEEDBACK_EMAIL} with the subject already filled in. */
export function feedbackMailto(subject: string): string {
  return `mailto:${FEEDBACK_EMAIL}?subject=${encodeURIComponent(subject)}`
}
