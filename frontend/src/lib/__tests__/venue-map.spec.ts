import { CookingPot, Cross, DoorOpen, Info, MapPin, SquareParking, Toilet } from '@lucide/vue'
import { describe, expect, it } from 'vitest'

import {
  GENERIC_MARKER_KINDS,
  MARKER_KINDS,
  STAFFING_CLASSES,
  STAFFING_LEGEND,
  clamp01,
  clientToImage,
  cropAround,
  estimateTextWidth,
  fitViewBox,
  markerIcon,
  markerKindLabelKey,
  panBy,
  planImageUrl,
  sharedLocationId,
  staffingLabelKey,
  staffingStatus,
  templateImageUrl,
  toNormalised,
  unitsPerPixel,
  viewBoxToString,
  zoomAt,
} from '@/lib/venue-map'

const W = 1000
const H = 500

describe('marker vocabulary', () => {
  it('lists every API kind once, location first', () => {
    expect(MARKER_KINDS[0]).toBe('location')
    expect(new Set(MARKER_KINDS).size).toBe(7)
  })

  it('generic kinds are every kind except location', () => {
    expect(GENERIC_MARKER_KINDS).toEqual([
      'entrance',
      'info_desk',
      'first_aid',
      'toilets',
      'parking',
      'kitchen',
    ])
  })

  it.each([
    ['location', MapPin],
    ['entrance', DoorOpen],
    ['info_desk', Info],
    ['first_aid', Cross],
    ['toilets', Toilet],
    ['parking', SquareParking],
    ['kitchen', CookingPot],
  ])('maps %s to its icon', (kind, icon) => {
    expect(markerIcon(kind)).toBe(icon)
  })

  it('falls back to a pin for an unknown kind', () => {
    expect(markerIcon('stage')).toBe(MapPin)
  })

  it('builds camelCase label keys from snake_case kinds', () => {
    expect(markerKindLabelKey('first_aid')).toBe('venueMap.markerKinds.firstAid')
    expect(markerKindLabelKey('location')).toBe('venueMap.markerKinds.location')
  })
})

describe('planImageUrl', () => {
  it('carries the etag as a cache buster', () => {
    expect(planImageUrl({ id: 'p1', image_etag: 'abc' })).toBe(
      `${import.meta.env.VITE_API_URL}/venue-plans/p1/image?v=abc`,
    )
  })

  it.each([
    ['null plan', null],
    ['no etag', { id: 'p1' }],
    ['null etag', { id: 'p1', image_etag: null }],
  ])('is null for %s', (_label, plan) => {
    expect(planImageUrl(plan)).toBeNull()
  })
})

describe('templateImageUrl', () => {
  it('points at the template picture with the etag as a cache buster', () => {
    expect(templateImageUrl({ id: 't1', image_etag: 'abc' })).toBe(
      `${import.meta.env.VITE_API_URL}/venue-templates/t1/image?v=abc`,
    )
  })

  it('is null without a picture', () => {
    expect(templateImageUrl(null)).toBeNull()
    expect(templateImageUrl({ id: 't1', image_etag: null })).toBeNull()
  })
})

describe('clamp01', () => {
  it.each([
    [-0.5, 0],
    [0.25, 0.25],
    [1.5, 1],
    [Number.NaN, 0],
  ])('clamps %s to %s', (input, expected) => {
    expect(clamp01(input)).toBe(expected)
  })
})

describe('fitViewBox / viewBoxToString', () => {
  it('shows the whole image', () => {
    expect(fitViewBox(W, H)).toEqual({ x: 0, y: 0, w: W, h: H })
    expect(viewBoxToString(fitViewBox(W, H))).toBe('0 0 1000 500')
  })
})

describe('panBy', () => {
  it('moves the box', () => {
    const vb = { x: 100, y: 100, w: 200, h: 100 }
    expect(panBy(vb, 50, -20, W, H)).toEqual({ x: 150, y: 80, w: 200, h: 100 })
  })

  it('keeps at least 10% of the image visible on each side', () => {
    const vb = { x: 0, y: 0, w: 200, h: 100 }
    // Dragged far past the right/bottom edge: the box stops at 90%.
    expect(panBy(vb, 5000, 5000, W, H)).toMatchObject({ x: 900, y: 450 })
    // Dragged far past the left/top edge: 10% of the image still shows.
    expect(panBy(vb, -5000, -5000, W, H)).toMatchObject({ x: -100, y: -50 })
  })
})

describe('zoomAt', () => {
  const fit = fitViewBox(W, H)

  it('zooms in around the given point, keeping it fixed', () => {
    const vb = zoomAt(fit, 2, 250, 125, W, H, 100, W)
    expect(vb).toEqual({ x: 125, y: 62.5, w: 500, h: 250 })
    // The anchor sits at the same relative position before and after.
    expect((250 - vb.x) / vb.w).toBeCloseTo((250 - fit.x) / fit.w)
  })

  it('clamps to the minimum width (maximum zoom)', () => {
    const vb = zoomAt(fit, 100, 500, 250, W, H, 125, W)
    expect(vb.w).toBe(125)
    expect(vb.h).toBe(62.5)
  })

  it('clamps to the maximum width (fully zoomed out)', () => {
    const zoomed = { x: 400, y: 200, w: 200, h: 100 }
    expect(zoomAt(zoomed, 0.01, 500, 250, W, H, 125, W)).toEqual(fit)
  })

  it('ignores a nonsensical factor or an empty box', () => {
    expect(zoomAt(fit, 0, 0, 0, W, H, 1, W)).toBe(fit)
    expect(zoomAt(fit, Number.NaN, 0, 0, W, H, 1, W)).toBe(fit)
    const empty = { x: 0, y: 0, w: 0, h: 0 }
    expect(zoomAt(empty, 2, 0, 0, W, H, 1, W)).toBe(empty)
  })
})

describe('toNormalised', () => {
  it('divides by the image size', () => {
    expect(toNormalised({ x: 250, y: 400 }, W, H)).toEqual({ x: 0.25, y: 0.8 })
  })

  it('clamps points outside the image', () => {
    expect(toNormalised({ x: -10, y: 900 }, W, H)).toEqual({ x: 0, y: 1 })
  })

  it('returns the origin for an empty image', () => {
    expect(toNormalised({ x: 5, y: 5 }, 0, 0)).toEqual({ x: 0, y: 0 })
  })
})

describe('cropAround', () => {
  it('centres a 16:9 box spanning 35% of the width on the point', () => {
    const vb = cropAround(0.5, 0.5, W, H)
    expect(vb.w).toBeCloseTo(350)
    expect(vb.h).toBeCloseTo(350 / (16 / 9))
    expect(vb.x + vb.w / 2).toBeCloseTo(500)
    expect(vb.y + vb.h / 2).toBeCloseTo(250)
  })

  it('shifts the box inside the image near an edge', () => {
    const vb = cropAround(0, 1, W, H)
    expect(vb.x).toBe(0)
    expect(vb.y + vb.h).toBeCloseTo(H)
  })

  it('shrinks to the image height for a very wide image', () => {
    const vb = cropAround(0.5, 0.5, 4000, 100, 0.5)
    expect(vb.h).toBe(100)
    expect(vb.w).toBeCloseTo(100 * (16 / 9))
  })

  it('never gets wider than the image', () => {
    const vb = cropAround(0.5, 0.5, 100, 100, 2, 1)
    expect(vb).toEqual({ x: 0, y: 0, w: 100, h: 100 })
  })

  it('caps the width at the image when the aspect allows a wider box', () => {
    // fraction 3 → w=300, h=150 ≤ H; then capped to the 100 px image width.
    const vb = cropAround(0.5, 0.5, 100, 1000, 3, 2)
    expect(vb.w).toBe(100)
    expect(vb.h).toBe(50)
  })
})

describe('unitsPerPixel', () => {
  it('uses the larger ratio, as preserveAspectRatio="meet" does', () => {
    expect(unitsPerPixel({ x: 0, y: 0, w: 1000, h: 500 }, 500, 500)).toBe(2)
    expect(unitsPerPixel({ x: 0, y: 0, w: 1000, h: 500 }, 1000, 250)).toBe(2)
  })

  it('falls back to 1 before layout', () => {
    expect(unitsPerPixel({ x: 0, y: 0, w: 1000, h: 500 }, 0, 0)).toBe(1)
  })
})

describe('clientToImage', () => {
  it('maps a client point through an exactly fitting box', () => {
    const rect = { left: 10, top: 20, width: 500, height: 250 }
    expect(clientToImage(fitViewBox(W, H), rect, 10, 20)).toEqual({ x: 0, y: 0 })
    expect(clientToImage(fitViewBox(W, H), rect, 260, 145)).toEqual({ x: 500, y: 250 })
  })

  it('accounts for the letterbox bars of preserveAspectRatio="meet"', () => {
    // A 1000×500 image in a 500×500 box: scale 2, bars of 125 px top and bottom.
    const rect = { left: 0, top: 0, width: 500, height: 500 }
    expect(clientToImage(fitViewBox(W, H), rect, 0, 125)).toEqual({ x: 0, y: 0 })
    expect(clientToImage(fitViewBox(W, H), rect, 500, 375)).toEqual({ x: 1000, y: 500 })
  })

  it('follows a panned and zoomed box', () => {
    const vb = { x: 200, y: 100, w: 500, h: 250 }
    const rect = { left: 0, top: 0, width: 500, height: 250 }
    expect(clientToImage(vb, rect, 250, 125)).toEqual({ x: 450, y: 225 })
  })

  it('treats an unlaid-out element as one unit per pixel', () => {
    const rect = { left: 5, top: 5, width: 0, height: 0 }
    expect(clientToImage(fitViewBox(W, H), rect, 15, 25)).toEqual({ x: 10, y: 20 })
  })
})

describe('sharedLocationId', () => {
  it('takes the task location while there are no shifts', () => {
    expect(sharedLocationId([], 'a')).toBe('a')
    expect(sharedLocationId([], null)).toBeNull()
    expect(sharedLocationId([], undefined)).toBeNull()
  })

  it('needs every shift at the same location', () => {
    expect(sharedLocationId([{ location_id: 'a' }, { location_id: 'a' }], 'b')).toBe('a')
    expect(sharedLocationId([{ location_id: 'a' }, { location_id: 'c' }], 'a')).toBeNull()
  })

  it('treats a shift without a location as somewhere else', () => {
    expect(sharedLocationId([{ location_id: 'a' }, { location_id: null }], 'a')).toBeNull()
    expect(sharedLocationId([{ location_id: null }, { location_id: 'a' }], 'a')).toBeNull()
    expect(sharedLocationId([{}], 'a')).toBeNull()
  })
})

describe('staffingStatus', () => {
  it('is none without shifts that day', () => {
    expect(staffingStatus(undefined)).toBe('none')
    expect(staffingStatus(null)).toBe('none')
    expect(staffingStatus({ booked: 0, capacity: 0 })).toBe('none')
  })

  it('is full once every slot is booked', () => {
    expect(staffingStatus({ booked: 4, capacity: 4 })).toBe('full')
    expect(staffingStatus({ booked: 5, capacity: 4 })).toBe('full')
  })

  it('is partial from half the slots, short below', () => {
    expect(staffingStatus({ booked: 4, capacity: 8 })).toBe('partial')
    expect(staffingStatus({ booked: 3, capacity: 4 })).toBe('partial')
    expect(staffingStatus({ booked: 3, capacity: 7 })).toBe('short')
    expect(staffingStatus({ booked: 2, capacity: 9 })).toBe('short')
    expect(staffingStatus({ booked: 0, capacity: 4 })).toBe('short')
  })

  it('names and colours every status', () => {
    expect(STAFFING_LEGEND).toEqual(['full', 'partial', 'short'])
    expect(staffingLabelKey('short')).toBe('venueMap.staffing.short')
    for (const status of ['full', 'partial', 'short', 'none'] as const) {
      expect(STAFFING_CLASSES[status].fill).toMatch(/^fill-staff-/)
    }
  })
})

describe('estimateTextWidth', () => {
  it('grows with the text and the font size', () => {
    expect(estimateTextWidth('', 12)).toBe(0)
    expect(estimateTextWidth('Info', 12)).toBeLessThan(estimateTextWidth('Information', 12))
    expect(estimateTextWidth('Bar', 24)).toBeGreaterThan(estimateTextWidth('Bar', 12))
    // Wide letters count for more than narrow ones.
    expect(estimateTextWidth('MMM', 12)).toBeGreaterThan(estimateTextWidth('iii', 12))
  })
})
