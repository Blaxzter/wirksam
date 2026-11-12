/**
 * The shift lengths, in minutes, a schedule offers to choose from. Up to four
 * hours, since a stand at a festival is often staffed in three or four.
 */
export const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120, 180, 240]

/**
 * The shift lengths a dropdown offers, with the one already set among them.
 *
 * A task set to 5-hour shifts is not in DURATION_OPTIONS, and reka-ui derives
 * the trigger label from a matching SelectItem: with no match the box renders
 * empty while the preview still uses the real number.
 */
export function durationOptions(current: number | null | undefined): number[] {
  const options = new Set(DURATION_OPTIONS)
  if (current && current > 0) options.add(current)
  return [...options].sort((a, b) => a - b)
}
