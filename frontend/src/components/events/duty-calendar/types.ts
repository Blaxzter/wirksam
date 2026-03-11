import type { EventGroupRead, EventRead } from '@/client/types.gen'

export interface BookingCalendarItem {
  id: string
  slotId: string
  date: string
  title: string
  startTime?: string | null | undefined
  endTime?: string | null | undefined
}

export interface CalendarDay {
  date: Date | null
  dateStr: string | null
  events: EventRead[]
  groups: EventGroupRead[]
  bookings: BookingCalendarItem[]
}

export interface GroupBar {
  group: EventGroupRead
  startCol: number
  span: number
  lane: number
  isStart: boolean
  isEnd: boolean
}

export interface EventBar {
  event: EventRead
  startCol: number
  span: number
  lane: number
  isStart: boolean
  isEnd: boolean
}

export interface CalendarWeek {
  days: CalendarDay[]
  groupBars: GroupBar[]
  eventBars: EventBar[]
  barLaneCount: number
  eventBarLaneCount: number
}

export type ViewMode = 'month' | 'week' | 'day'

export interface DutyCalendarEmits {
  navigateEvent: [event: EventRead]
  navigateGroup: [group: EventGroupRead]
  navigateBooking: [booking: BookingCalendarItem]
}

export const EMPTY_DAY: CalendarDay = {
  date: null,
  dateStr: null,
  events: [],
  groups: [],
  bookings: [],
}

export function computeGroupBars(weekDays: CalendarDay[]): GroupBar[] {
  const seen = new Set<string>()
  const groupsInWeek: EventGroupRead[] = []
  for (const day of weekDays) {
    for (const g of day.groups) {
      if (!seen.has(g.id)) {
        seen.add(g.id)
        groupsInWeek.push(g)
      }
    }
  }

  return groupsInWeek.map((group, lane) => {
    let startCol = -1
    let endCol = -1
    for (let col = 0; col < weekDays.length; col++) {
      if (weekDays[col].groups.some((g) => g.id === group.id)) {
        if (startCol === -1) startCol = col
        endCol = col
      }
    }

    const startDay = weekDays[startCol]
    const endDay = weekDays[endCol]
    const isStart = startDay.dateStr === group.start_date
    const isEnd = endDay.dateStr === group.end_date

    return { group, startCol, span: endCol - startCol + 1, lane, isStart, isEnd }
  })
}

export function computeEventBars(weekDays: CalendarDay[]): EventBar[] {
  const seen = new Set<string>()
  const multiDayEvents: EventRead[] = []
  for (const day of weekDays) {
    for (const e of day.events) {
      if (!seen.has(e.id) && e.start_date !== e.end_date) {
        seen.add(e.id)
        multiDayEvents.push(e)
      }
    }
  }

  return multiDayEvents.map((event, lane) => {
    let startCol = -1
    let endCol = -1
    for (let col = 0; col < weekDays.length; col++) {
      if (weekDays[col].events.some((e) => e.id === event.id)) {
        if (startCol === -1) startCol = col
        endCol = col
      }
    }

    const startDay = weekDays[startCol]
    const endDay = weekDays[endCol]
    const isStart = startDay.dateStr === event.start_date
    const isEnd = endDay.dateStr === event.end_date

    return { event, startCol, span: endCol - startCol + 1, lane, isStart, isEnd }
  })
}

/** Check if an event spans multiple days */
export function isMultiDayEvent(event: EventRead): boolean {
  return event.start_date !== event.end_date
}

export function dateToStr(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function isToday(date: Date | null): boolean {
  if (!date) return false
  return dateToStr(date) === dateToStr(new Date())
}

function stripSeconds(time: string): string {
  // "HH:MM:SS" → "HH:MM"
  const parts = time.split(':')
  return parts.length >= 2 ? `${parts[0]}:${parts[1]}` : time
}

export function formatTimeRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  const s = start ? stripSeconds(start) : null
  const e = end ? stripSeconds(end) : null
  if (s && e) return `${s} – ${e}`
  if (s) return s
  if (e) return `– ${e}`
  return ''
}

export function statusVariant(status?: string) {
  switch (status) {
    case 'published':
      return 'default' as const
    case 'draft':
      return 'secondary' as const
    case 'archived':
      return 'outline' as const
    default:
      return 'secondary' as const
  }
}
