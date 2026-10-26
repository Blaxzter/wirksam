import type {
  EventTeamMemberRead,
  EventTeamRead,
  TeamCheckRead,
  TeamRequirementIn,
  TeamRequirementRead,
} from '@/client/types.gen'

/** Who the review dialog is about: a requester, or someone being added. */
export interface ReviewPerson {
  user_id: string
  name: string
  email?: string | null
  avatar_etag?: string | null
}

/** The server's cap; the form stops offering "Add" there. */
export const MAX_REQUIREMENTS = 10

/** What `PUT …/join/documents/{requirement_id}` takes (checked again server-side). */
export const MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
export const DOCUMENT_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp']

export type RequirementPresetKey = 'policeCertificate' | 'firstAid' | 'drivingLicence'

/**
 * Ready-made requirements for the team form. Label and description come from
 * `teams.presets.<key>` in the active language; the flags are fixed.
 *
 * The police certificate deliberately takes no file: §72a SGB VIII lets an
 * organiser *see* an extended certificate and note that they did, not keep a
 * copy of it.
 */
export const REQUIREMENT_PRESETS: readonly {
  key: RequirementPresetKey
  ask_issue_date: boolean
  valid_for_years: number | null
  accepts_document: boolean
}[] = [
  { key: 'policeCertificate', ask_issue_date: true, valid_for_years: 5, accepts_document: false },
  { key: 'firstAid', ask_issue_date: true, valid_for_years: 2, accepts_document: true },
  { key: 'drivingLicence', ask_issue_date: false, valid_for_years: null, accepts_document: false },
]

/** One requirement row in the team form; `id` is kept for existing ones. */
export type RequirementDraft = Required<Omit<TeamRequirementIn, 'id' | 'description'>> & {
  id: string | null
  description: string
  /** Stable key for `v-for`, also for rows that have no id yet. */
  key: string
}

let draftCounter = 0

export function newDraft(fields: Partial<RequirementDraft> = {}): RequirementDraft {
  draftCounter += 1
  return {
    id: null,
    label: '',
    description: '',
    ask_issue_date: false,
    valid_for_years: null,
    accepts_document: false,
    key: `draft-${draftCounter}`,
    ...fields,
  }
}

export function draftFromRequirement(req: TeamRequirementRead): RequirementDraft {
  return newDraft({
    id: req.id,
    label: req.label,
    description: req.description ?? '',
    ask_issue_date: req.ask_issue_date,
    valid_for_years: req.valid_for_years ?? null,
    accepts_document: req.accepts_document,
    key: req.id,
  })
}

/** The API body for one draft; blank optional text becomes `null`. */
export function draftToPayload(draft: RequirementDraft): TeamRequirementIn {
  const years = draft.valid_for_years
  return {
    ...(draft.id ? { id: draft.id } : {}),
    label: draft.label.trim(),
    description: draft.description.trim() || null,
    ask_issue_date: draft.ask_issue_date,
    valid_for_years: years && years > 0 ? Math.floor(years) : null,
    accepts_document: draft.accepts_document,
  }
}

/** Labels compared the way the server does: ignoring case and extra spaces. */
export function labelKey(label: string): string {
  return label.split(/\s+/).filter(Boolean).join(' ').toLocaleLowerCase()
}

/** Today as `YYYY-MM-DD` in the viewer's time zone. */
export function todayIso(now: Date = new Date()): string {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** `iso` plus whole years; 29 February falls back to the 28th, as on the server. */
export function addYears(iso: string, years: number): string {
  const [y, m, d] = iso.split('-').map(Number) as [number, number, number]
  const year = y + years
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0
  const day = m === 2 && d === 29 && !leap ? 28 : d
  return `${year}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/**
 * When a check recorded today would run out: counted from the issue date when
 * the requirement asks for one, else from today. `null` when it never does.
 */
export function expiryFor(
  req: Pick<TeamRequirementRead, 'valid_for_years' | 'ask_issue_date'>,
  issuedOn: string | null,
  today: string = todayIso(),
): string | null {
  if (!req.valid_for_years) return null
  return addYears((req.ask_issue_date && issuedOn) || today, req.valid_for_years)
}

/** Why an entered issue date would be refused, if it would. */
export function issueDateProblem(
  req: Pick<TeamRequirementRead, 'valid_for_years' | 'ask_issue_date'>,
  issuedOn: string | null,
  today: string = todayIso(),
): 'future' | 'expired' | null {
  if (!issuedOn) return null
  if (issuedOn > today) return 'future'
  const expires = expiryFor(req, issuedOn, today)
  return expires !== null && expires < today ? 'expired' : null
}

/** A reusable check from another team for this requirement, if one is valid. */
export function reusableCheckFor(
  req: TeamRequirementRead,
  reusable: TeamCheckRead[] | undefined,
): TeamCheckRead | undefined {
  const key = labelKey(req.label)
  return reusable?.find((c) => !c.expired && labelKey(c.label) === key)
}

export function displayName(row: Pick<EventTeamMemberRead, 'user_name' | 'user_email'>): string {
  return row.user_name || row.user_email || '?'
}

/** First word of a name, for "Approve Carla". */
export function firstName(name: string): string {
  return name.replace(/^\[[^\]]*\]\s*/, '').split(/\s+/)[0] || name
}

export { initials } from '@/lib/format'

/** Teams with requirements need the review dialog; plain ones are decided inline. */
export function needsReview(team: Pick<EventTeamRead, 'requirements'> | undefined): boolean {
  return (team?.requirements?.length ?? 0) > 0
}

/** "a, b and c" in the active language. */
export function joinNames(names: string[], locale: string): string {
  try {
    return new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(names)
  } catch {
    return names.join(', ')
  }
}
