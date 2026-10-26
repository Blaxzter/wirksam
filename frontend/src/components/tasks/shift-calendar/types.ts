/** Visible date range emitted by the calendar for data fetching. */
export interface DateRange {
  from: string // YYYY-MM-DD
  to: string // YYYY-MM-DD
}

/** Minimal task shape used by the calendar — structurally satisfied by `TaskRead`. */
export interface CalendarTask {
  id: string
  name: string
  status?: string
  description?: string | null
  location?: string | null
  start_date: string
  end_date: string
  /** The team the task is reserved for, and whether that locks the viewer out. */
  team_name?: string | null
  locked_by_team?: boolean
}

/** Minimal task event shape used by the calendar. */
export interface CalendarEvent {
  id: string
  name: string
  start_date: string
  end_date: string
}

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
  tasks: CalendarTask[]
  events: CalendarEvent[]
  bookings: BookingCalendarItem[]
}

export interface EventBar {
  event: CalendarEvent
  startCol: number
  span: number
  lane: number
  isStart: boolean
  isEnd: boolean
}

export interface TaskBar {
  task: CalendarTask
  startCol: number
  span: number
  lane: number
  isStart: boolean
  isEnd: boolean
}

export interface CalendarWeek {
  days: CalendarDay[]
  groupBars: EventBar[]
  eventBars: TaskBar[]
  barLaneCount: number
  eventBarLaneCount: number
}

export type ViewMode = 'month' | 'week' | 'day'

export interface ShiftCalendarEmits {
  navigateTask: [task: CalendarTask]
  navigateGroup: [event: CalendarEvent]
  navigateBooking: [booking: BookingCalendarItem]
}

export const EMPTY_DAY: CalendarDay = {
  date: null,
  dateStr: null,
  tasks: [],
  events: [],
  bookings: [],
}

export function computeEventBars(weekDays: CalendarDay[]): EventBar[] {
  const seen = new Set<string>()
  const groupsInWeek: CalendarEvent[] = []
  for (const day of weekDays) {
    for (const g of day.events) {
      if (!seen.has(g.id)) {
        seen.add(g.id)
        groupsInWeek.push(g)
      }
    }
  }

  return groupsInWeek.map((event, lane) => {
    let startCol = -1
    let endCol = -1
    for (let col = 0; col < weekDays.length; col++) {
      if (weekDays[col].events.some((g) => g.id === event.id)) {
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

export function computeTaskBars(weekDays: CalendarDay[]): TaskBar[] {
  const seen = new Set<string>()
  const multiDayTasks: CalendarTask[] = []
  for (const day of weekDays) {
    for (const e of day.tasks) {
      if (!seen.has(e.id) && e.start_date !== e.end_date) {
        seen.add(e.id)
        multiDayTasks.push(e)
      }
    }
  }

  return multiDayTasks.map((task, lane) => {
    let startCol = -1
    let endCol = -1
    for (let col = 0; col < weekDays.length; col++) {
      if (weekDays[col].tasks.some((e) => e.id === task.id)) {
        if (startCol === -1) startCol = col
        endCol = col
      }
    }

    const startDay = weekDays[startCol]
    const endDay = weekDays[endCol]
    const isStart = startDay.dateStr === task.start_date
    const isEnd = endDay.dateStr === task.end_date

    return { task, startCol, span: endCol - startCol + 1, lane, isStart, isEnd }
  })
}

/** Check if a task spans multiple days */
export function isMultiDayTask(task: CalendarTask): boolean {
  return task.start_date !== task.end_date
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
