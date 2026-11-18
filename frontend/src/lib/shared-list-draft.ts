/**
 * The shared-list wizard's draft: what the organiser has chosen so far, how it
 * starts (blank, from a list being edited or copied), what keeps the settings
 * step from being done, and the request bodies it turns into.
 *
 * The selection half (tasks and excluded shifts) follows the rules in
 * `shared-list-selection.ts`; this module only carries it.
 */
import type { SharedListCreate, SharedListDetail, SharedListUpdate } from '@/client/types.gen'
import type { PickedTask } from '@/lib/shared-list-selection'

export type AskMode = NonNullable<SharedListCreate['ask_email']>
export type ShowNames = NonNullable<SharedListCreate['show_names']>
export type EndsMode = NonNullable<SharedListCreate['ends_mode']>

/** The API's limits on the free-text fields (`app/schemas/shared_list.py`). */
export const TITLE_MAX = 120
export const INTRO_MAX = 1000
export const SHARE_NOTE_MAX = 120

export interface SharedListDraft {
  /** In list order: the order the public page shows the tasks in. */
  tasks: PickedTask[]
  excluded: Set<string>
  title: string
  /** Typed by hand: from then on the title no longer follows the tasks. */
  titleTouched: boolean
  intro: string
  shareNote: string
  askEmail: AskMode
  askPhone: AskMode
  showNames: ShowNames
  /** `null` is "as many as are free", the default (correction (b)). */
  maxPerPerson: number | null
  endsMode: EndsMode
  /** `YYYY-MM-DD`; only read while `endsMode` is `date`. */
  endsOn: string | null
}

export function blankDraft(tasks: readonly PickedTask[] = []): SharedListDraft {
  return {
    tasks: [...tasks],
    excluded: new Set(),
    title: '',
    titleTouched: false,
    intro: '',
    shareNote: '',
    askEmail: 'required',
    askPhone: 'off',
    showNames: 'none',
    maxPerPerson: null,
    endsMode: 'last_shift',
    endsOn: null,
  }
}

/**
 * A draft holding what `list` has, title counted as typed: for editing it, or
 * copying it. A task the list can no longer offer comes along marked, so the
 * wizard can ask for it to be taken out rather than have the API refuse it.
 */
export function draftFromDetail(list: SharedListDetail): SharedListDraft {
  return {
    tasks: list.detail_tasks.map((task) => ({
      id: task.id,
      name: task.name,
      unavailable: task.not_offered_reason,
    })),
    excluded: new Set(list.excluded_shift_ids),
    title: list.title,
    titleTouched: true,
    intro: list.intro ?? '',
    shareNote: list.share_note ?? '',
    askEmail: list.ask_email,
    askPhone: list.ask_phone,
    showNames: list.show_names,
    maxPerPerson: list.max_per_person,
    endsMode: list.ends_mode,
    endsOn: list.ends_on,
  }
}

export type SettingsBlocker =
  | { kind: 'no_title' }
  | { kind: 'ends_on_missing' }
  | { kind: 'ends_on_past' }
  | { kind: 'ends_on_after_last'; lastDate: string }

/**
 * What keeps the settings step from being saved, in the order the wizard
 * names them. `today` is the date on the event's clock and `lastDate` the day
 * of the last shift the list offers; both are `YYYY-MM-DD`.
 *
 * `checkClosing: false` leaves the closing day alone, for an edit that changes
 * neither it nor the selection: the API does not check it then either, so a
 * list that closed yesterday can still have its text corrected.
 */
export function settingsBlockers(
  draft: Pick<SharedListDraft, 'title' | 'endsMode' | 'endsOn'>,
  context: { today: string; lastDate: string | null; checkClosing?: boolean },
): SettingsBlocker[] {
  const blockers: SettingsBlocker[] = []
  if (!draft.title.trim()) blockers.push({ kind: 'no_title' })
  if (draft.endsMode === 'date' && context.checkClosing !== false) {
    if (!draft.endsOn) blockers.push({ kind: 'ends_on_missing' })
    else if (draft.endsOn < context.today) blockers.push({ kind: 'ends_on_past' })
    else if (context.lastDate && draft.endsOn > context.lastDate) {
      blockers.push({ kind: 'ends_on_after_last', lastDate: context.lastDate })
    }
  }
  return blockers
}

/**
 * The fields of an edit that make the API check the selection again, the
 * closing day with it (`_SELECTION_FIELDS` in `logic/shared_lists/manage.py`).
 */
export const SELECTION_FIELDS = ['task_ids', 'excluded_shift_ids', 'ends_mode', 'ends_on'] as const

/** Every field of a create request, set: the shape both requests are built from. */
export type SharedListPayload = Required<SharedListCreate>

/**
 * The request body for `draft`, with `excludedShiftIds` as worked out by
 * `pruneExcluded`. Text is trimmed and blank text becomes `null`, as the API
 * stores it; the closing day goes only with a list that closes on a day.
 */
export function toPayload(
  draft: SharedListDraft,
  excludedShiftIds: readonly string[],
): SharedListPayload {
  return {
    title: draft.title.trim(),
    intro: draft.intro.trim() || null,
    share_note: draft.shareNote.trim() || null,
    task_ids: draft.tasks.map((task) => task.id),
    excluded_shift_ids: [...excludedShiftIds].sort(),
    ask_email: draft.askEmail,
    ask_phone: draft.askPhone,
    show_names: draft.showNames,
    max_per_person: draft.maxPerPerson,
    ends_mode: draft.endsMode,
    ends_on: draft.endsMode === 'date' ? draft.endsOn : null,
  }
}

/**
 * Only what changed between two payloads, for `PATCH /shared-lists/{id}`.
 *
 * Sending an unchanged selection would still make the API check it again, so
 * a new title could be refused because a shift filled up meanwhile.
 */
export function changedFields(
  next: SharedListPayload,
  before: SharedListPayload,
): SharedListUpdate {
  const changed = Object.entries(next).filter(
    ([key, value]) =>
      JSON.stringify(value) !== JSON.stringify(before[key as keyof SharedListPayload]),
  )
  return Object.fromEntries(changed) as SharedListUpdate
}

/** One string per state of the draft, to tell whether anything is left unsaved. */
export function draftSignature(draft: SharedListDraft): string {
  return JSON.stringify(toPayload(draft, [...draft.excluded]))
}
