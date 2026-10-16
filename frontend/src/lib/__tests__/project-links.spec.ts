import { describe, expect, it } from 'vitest'

import { FEEDBACK_EMAIL, REPO_URL, feedbackMailto, newIssueUrl } from '@/lib/project-links'

describe('newIssueUrl', () => {
  it('opens the named issue form on the upstream repository', () => {
    expect(newIssueUrl('feature_request.yml')).toBe(
      `${REPO_URL}/issues/new?template=feature_request.yml`,
    )
    expect(newIssueUrl('bug_report.yml')).toBe(`${REPO_URL}/issues/new?template=bug_report.yml`)
  })
})

describe('feedbackMailto', () => {
  it('addresses the feedback inbox with an encoded subject', () => {
    expect(feedbackMailto('WirkSam: Feedback & Ideen')).toBe(
      `mailto:${FEEDBACK_EMAIL}?subject=WirkSam%3A%20Feedback%20%26%20Ideen`,
    )
  })
})
