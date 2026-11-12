import type { DocDevice, DocShot } from './doc-types'

/** Where a visitor's choice between the two kinds of screenshot is kept. */
export const DEVICE_KEY = 'wirksam-doc-device'

/** The file a screen was saved under on a device, without `-light`/`-dark`. */
export function shotFile(name: string, device: DocDevice): string {
  return device === 'phone' ? `${name}-phone` : name
}

/** The device a screenshot is shown from: the one asked for, if it was taken on it. */
export function shotDevice(shot: DocShot, device: DocDevice): DocDevice {
  if (shot.devices[device]) return device
  return device === 'phone' ? 'desktop' : 'phone'
}

/** Whether a visitor can choose between the two for any of these screenshots. */
export function offersChoice(shots: DocShot[]): boolean {
  return shots.some((shot) => shot.devices.desktop && shot.devices.phone)
}

/**
 * Which screenshots a visitor sees first: what they chose last time, or else
 * what they are reading on.
 */
export function preferredDevice(stored: string | null, narrow: boolean): DocDevice {
  if (stored === 'desktop' || stored === 'phone') return stored
  return narrow ? 'phone' : 'desktop'
}
