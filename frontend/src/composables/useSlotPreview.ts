import { computed, ref, type Ref, watch } from 'vue'

export type RemainderMode = 'drop' | 'short' | 'extend'

export interface ScheduleConfig {
  eventName: string
  startDate: string // YYYY-MM-DD
  endDate: string // YYYY-MM-DD
  specificDates?: string[] // YYYY-MM-DD — when set, only these dates get slots
  defaultStartTime: string // HH:MM
  defaultEndTime: string // HH:MM
  slotDurationMinutes: number
  peoplePerSlot: number
  remainderMode: RemainderMode
  overrides: Array<{
    date: string // YYYY-MM-DD
    startTime: string // HH:MM
    endTime: string // HH:MM
  }>
}

export interface PreviewSlot {
  date: string
  startTime: string
  endTime: string
  title: string
}

export function slotKey(slot: PreviewSlot): string {
  return `${slot.date}|${slot.startTime}|${slot.endTime}`
}

/**
 * Composable that generates a client-side preview of duty slots
 * from a schedule configuration. Mirrors the backend slot_generator logic.
 */
export function useSlotPreview(config: Ref<ScheduleConfig>) {
  const previewSlots = computed<PreviewSlot[]>(() => {
    const { eventName, startDate, endDate, defaultStartTime, defaultEndTime, slotDurationMinutes } =
      config.value

    if (!startDate || !endDate || !defaultStartTime || !defaultEndTime || !slotDurationMinutes) {
      return []
    }

    if (slotDurationMinutes < 1) return []

    const overrideMap = new Map<string, { startTime: string; endTime: string }>()
    for (const o of config.value.overrides) {
      overrideMap.set(o.date, { startTime: o.startTime, endTime: o.endTime })
    }

    const slots: PreviewSlot[] = []
    const specificDatesSet = config.value.specificDates?.length
      ? new Set(config.value.specificDates)
      : null

    const current = new Date(startDate)
    const end = new Date(endDate)

    while (current <= end) {
      const dateStr = formatDate(current)

      // If specific dates are set, skip dates not in the list
      if (specificDatesSet && !specificDatesSet.has(dateStr)) {
        current.setDate(current.getDate() + 1)
        continue
      }

      const override = overrideMap.get(dateStr)
      const dayStart = override ? override.startTime : defaultStartTime
      const dayEnd = override ? override.endTime : defaultEndTime

      const daySlots = generateSlotsForDay(eventName, dateStr, dayStart, dayEnd, slotDurationMinutes, config.value.remainderMode)
      slots.push(...daySlots)

      current.setDate(current.getDate() + 1)
    }

    return slots
  })

  // Excluded slots tracking
  const excludedSlots = ref(new Set<string>())

  // Clear exclusions when the generated slots change (schedule reconfigured)
  watch(previewSlots, () => {
    const validKeys = new Set(previewSlots.value.map(slotKey))
    for (const key of excludedSlots.value) {
      if (!validKeys.has(key)) excludedSlots.value.delete(key)
    }
  })

  const toggleSlotExclusion = (slot: PreviewSlot) => {
    const key = slotKey(slot)
    if (excludedSlots.value.has(key)) {
      excludedSlots.value.delete(key)
    } else {
      excludedSlots.value.add(key)
    }
    // Trigger reactivity
    excludedSlots.value = new Set(excludedSlots.value)
  }

  const isSlotExcluded = (slot: PreviewSlot) => excludedSlots.value.has(slotKey(slot))

  const activeSlots = computed(() =>
    previewSlots.value.filter((s) => !excludedSlots.value.has(slotKey(s))),
  )

  const totalSlots = computed(() => activeSlots.value.length)

  const totalDays = computed(() => new Set(activeSlots.value.map((s) => s.date)).size)

  const slotsByDate = computed(() => {
    const grouped = new Map<string, PreviewSlot[]>()
    for (const slot of previewSlots.value) {
      const existing = grouped.get(slot.date) ?? []
      existing.push(slot)
      grouped.set(slot.date, existing)
    }
    return grouped
  })

  const hasRemainder = computed(() => {
    const { startDate, endDate, defaultStartTime, defaultEndTime, slotDurationMinutes } =
      config.value

    if (!startDate || !endDate || !defaultStartTime || !defaultEndTime || !slotDurationMinutes) {
      return false
    }
    if (slotDurationMinutes < 1) return false

    const overrideMap = new Map<string, { startTime: string; endTime: string }>()
    for (const o of config.value.overrides) {
      overrideMap.set(o.date, { startTime: o.startTime, endTime: o.endTime })
    }

    const specificDatesSet = config.value.specificDates?.length
      ? new Set(config.value.specificDates)
      : null

    const current = new Date(startDate)
    const end = new Date(endDate)

    while (current <= end) {
      const dateStr = formatDate(current)
      if (specificDatesSet && !specificDatesSet.has(dateStr)) {
        current.setDate(current.getDate() + 1)
        continue
      }

      const override = overrideMap.get(dateStr)
      const dayStart = override ? override.startTime : defaultStartTime
      const dayEnd = override ? override.endTime : defaultEndTime
      const totalMinutes = timeToMinutes(dayEnd) - timeToMinutes(dayStart)
      if (totalMinutes > 0 && totalMinutes % slotDurationMinutes !== 0) {
        return true
      }
      current.setDate(current.getDate() + 1)
    }

    return false
  })

  return {
    previewSlots,
    activeSlots,
    totalSlots,
    totalDays,
    slotsByDate,
    hasRemainder,
    excludedSlots,
    toggleSlotExclusion,
    isSlotExcluded,
  }
}

function formatDate(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function generateSlotsForDay(
  eventName: string,
  dateStr: string,
  startTime: string,
  endTime: string,
  durationMinutes: number,
  remainderMode: RemainderMode = 'drop',
): PreviewSlot[] {
  const slots: PreviewSlot[] = []
  const startMinutes = timeToMinutes(startTime)
  const endMinutes = timeToMinutes(endTime)

  if (startMinutes >= endMinutes) return []

  let current = startMinutes
  while (current + durationMinutes <= endMinutes) {
    const slotStart = minutesToTime(current)
    const slotEnd = minutesToTime(current + durationMinutes)
    slots.push({
      date: dateStr,
      startTime: slotStart,
      endTime: slotEnd,
      title: `${eventName} ${slotStart}-${slotEnd}`,
    })
    current += durationMinutes
  }

  // Handle remaining time that doesn't fill a full slot
  const remainder = endMinutes - current
  if (remainder > 0 && slots.length > 0) {
    if (remainderMode === 'short') {
      const slotStart = minutesToTime(current)
      const slotEnd = minutesToTime(endMinutes)
      slots.push({
        date: dateStr,
        startTime: slotStart,
        endTime: slotEnd,
        title: `${eventName} ${slotStart}-${slotEnd}`,
      })
    } else if (remainderMode === 'extend') {
      const last = slots[slots.length - 1]
      last.endTime = minutesToTime(endMinutes)
      last.title = `${eventName} ${last.startTime}-${last.endTime}`
    }
  } else if (remainder > 0 && slots.length === 0 && remainderMode === 'short') {
    // No full slots fit but there's time — create a short slot
    const slotStart = minutesToTime(startMinutes)
    const slotEnd = minutesToTime(endMinutes)
    slots.push({
      date: dateStr,
      startTime: slotStart,
      endTime: slotEnd,
      title: `${eventName} ${slotStart}-${slotEnd}`,
    })
  }

  return slots
}

function timeToMinutes(time: string): number {
  const [h, m] = time.split(':').map(Number)
  return h * 60 + m
}

function minutesToTime(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
