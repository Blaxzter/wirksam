/** Rows as the shared-list endpoints send them, for the component specs. */
import type {
  SharedListDetail,
  SharedListOverview,
  SharedListRow,
  SharedListSignup,
  SharedListTaskRow,
} from '@/client/types.gen'

export function listRow(id: string, patch: Partial<SharedListRow> = {}): SharedListRow {
  return {
    id,
    code: `code${id}`,
    title: `List ${id}`,
    share_note: 'Elternchat 3b',
    status: 'live',
    effective_status: 'live',
    ends_mode: 'last_shift',
    ends_on: null,
    closes_at: '2026-12-05T14:00:00',
    expires_soon: false,
    is_full: false,
    created_at: '2026-11-01T09:00:00',
    created_by_name: 'Anna',
    tasks: [{ id: 't1', name: 'Kuchen' }],
    only_days: null,
    excluded_shift_count: 0,
    capacity: 10,
    free: 4,
    signup_count: 6,
    guest_count: 6,
    view_count: 12,
    issue: null,
    access: 'admin',
    ...patch,
  }
}

export function listDetail(id: string, patch: Partial<SharedListDetail> = {}): SharedListDetail {
  return {
    ...listRow(id),
    intro: null,
    ask_email: 'required',
    ask_phone: 'off',
    show_names: 'none',
    max_per_person: null,
    rotated_at: null,
    paused_at: null,
    ended_at: null,
    task_ids: ['t1'],
    excluded_shift_ids: [],
    detail_tasks: [
      {
        id: 't1',
        name: 'Kuchen',
        offered: true,
        not_offered_reason: null,
        shift_count: 3,
        capacity: 10,
        free: 4,
        only_days: null,
      },
    ],
    event: {
      id: 'e1',
      name: 'Adventsbasar',
      start_date: '2026-12-05',
      end_date: '2026-12-06',
      timezone: 'Europe/Berlin',
    },
    ...patch,
  }
}

export function overview(patch: Partial<SharedListOverview> = {}): SharedListOverview {
  return {
    summary: { live_lists: 1, active_lists: 2, signups: 6, guests: 6, free_in_live: 4 },
    unshared: { task_count: 0, free: 0, task_names: [] },
    can_create: true,
    can_pause_all: true,
    is_admin: true,
    managers_share_lists: true,
    event_timezone: 'Europe/Berlin',
    ...patch,
  }
}

export function taskRow(id: string, patch: Partial<SharedListTaskRow> = {}): SharedListTaskRow {
  return {
    id,
    name: `Task ${id}`,
    location: 'Aula',
    manager_names: ['Jonas'],
    shift_count: 2,
    dates: ['2026-12-05'],
    capacity: 6,
    free: 3,
    team: null,
    lists: [],
    ended_list_count: 0,
    stranded_free: 0,
    unlisted_free: 0,
    can_share: true,
    ...patch,
  }
}

export function signup(id: string, patch: Partial<SharedListSignup> = {}): SharedListSignup {
  return {
    booking_id: id,
    name: 'Mia Berger',
    erased: false,
    email: 'mia@example.org',
    phone: null,
    task_id: 't1',
    task_name: 'Kuchen',
    shift_id: 's1',
    shift_date: '2026-12-05',
    start_time: '10:00:00',
    end_time: '12:00:00',
    created_at: '2026-11-10T08:00:00',
    possible_duplicate: false,
    can_remove: true,
    pooled_signups: 0,
    ...patch,
  }
}

/** `window.matchMedia` answering every query with `matches`. */
export function stubMatchMedia(matches: () => boolean) {
  window.matchMedia = ((media: string) => ({
    matches: matches(),
    media,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
