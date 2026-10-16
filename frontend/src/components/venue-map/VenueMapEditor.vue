<script setup lang="ts">
import {
  type ComponentPublicInstance,
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  useTemplateRef,
  watch,
} from 'vue'

import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  EllipsisVertical,
  ImageMinus,
  ImageOff,
  LayoutTemplate,
  Map as MapIcon,
  MapPin,
  Maximize,
  Minus,
  Pencil,
  Plus,
  SlidersHorizontal,
  Trash2,
  Undo2,
  X,
} from '@lucide/vue'
import { useEventListener } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthedImage } from '@/composables/useAuthedImage'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useLocations } from '@/composables/useLocations'
import { usePanZoom } from '@/composables/usePanZoom'
import { invalidatePlanShapes } from '@/composables/usePlanShapes'
import { type PressTarget, useShapeEditor } from '@/composables/useShapeEditor'
import { useShapeHistory } from '@/composables/useShapeHistory'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Skeleton } from '@/components/ui/skeleton'

import HintTooltip from '@/components/utils/HintTooltip.vue'
import VenueMarkerGlyph from '@/components/venue-map/VenueMarkerGlyph.vue'
import VenueMarkerPalette from '@/components/venue-map/VenueMarkerPalette.vue'
import VenueMarkerPill from '@/components/venue-map/VenueMarkerPill.vue'
import VenuePinHint from '@/components/venue-map/VenuePinHint.vue'
import VenuePlanSwitcher from '@/components/venue-map/VenuePlanSwitcher.vue'
import VenuePlanUpload from '@/components/venue-map/VenuePlanUpload.vue'
import VenueShapeLayer from '@/components/venue-map/VenueShapeLayer.vue'
import VenueDecorPalette from '@/components/venue-map/editor/VenueDecorPalette.vue'
import VenueDrawPreview from '@/components/venue-map/editor/VenueDrawPreview.vue'
import VenueEditHandles from '@/components/venue-map/editor/VenueEditHandles.vue'
import VenueEditorToolbar from '@/components/venue-map/editor/VenueEditorToolbar.vue'
import VenuePlanCreateDialog, {
  type PlanCreateValue,
} from '@/components/venue-map/editor/VenuePlanCreateDialog.vue'
import VenueShapeInspector from '@/components/venue-map/editor/VenueShapeInspector.vue'
import VenueTemplateNameDialog from '@/components/venue-map/editor/VenueTemplateNameDialog.vue'

import type {
  LocationRead,
  VenueMapRead,
  VenueMarkerRead,
  VenuePlanRead,
  VenuePlanShapesRead,
  VenueTemplateRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { propLabelKey } from '@/lib/venue-decor'
import {
  GENERIC_MARKER_KINDS,
  type MarkerKind,
  type Point,
  clamp01,
  markerKindLabelKey,
  planImageUrl,
  toNormalised,
} from '@/lib/venue-map'
import { RECT_HANDLES, type RectHandle } from '@/lib/venue-shape-edit'
import { planSize, planSurfaceClass, sortShapes } from '@/lib/venue-shapes'

/**
 * The venue map editor (event settings → "Map" tab, and the map page's edit
 * mode).
 *
 * An event has any number of plans (the grounds, one per floor, …). A plan is
 * drawn here — rooms, areas, paths and texts on a blank area — or starts from
 * an uploaded picture, and can be drawn on either way. On top go the pins.
 *
 * Drawing (`useShapeEditor` + `useShapeHistory`): tools for select,
 * rectangle, shape, line, text and decoration (trees, benches, tents, … from
 * a palette strip over the plan; never a place); snapping to a grid and to corners; every
 * step is one undoable command (Ctrl+Z / Ctrl+Shift+Z), saved optimistically
 * through the batch endpoint and rolled back if the server says no. Pins keep
 * their own endpoints and are not part of the undo history.
 *
 * Works with every input:
 * - mouse: draw with the primary button; drag the ground (select tool), the
 *   middle button or Space+drag pans; the wheel zooms;
 * - touch: one finger draws or drags, two pinch; polygons and lines get a
 *   bar with "Undo point", "Close shape"/"Finish" and "Cancel";
 * - keyboard: tools by letter (V R P L T D, G for snapping), shapes are
 *   buttons (Tab, Enter), arrows nudge, Delete removes, `[`/`]` reorder, Q/E
 *   turn and +/- resize a decoration; pins as before.
 *
 * Two homes: the "Map" tab of the event settings, and the map page itself,
 * where an admin flips into editing in place. `embedded` is the latter: no
 * heading, the editor fills its parent's height, and the `actions` slot (the
 * page's "Done" button) sits at the end of the plan row.
 *
 * Below the `lg` breakpoint the plan gets the whole height: the plans are a
 * menu, the tools sit under the plan (in thumb reach), and the side panel is a
 * bottom sheet over the plan that opens on demand (see "Phone sheet" below).
 *
 * In a demo (`sandbox`) the server refuses picture uploads, so the editor says
 * so instead of offering an upload that can only fail. Drawing is allowed.
 */
const props = withDefaults(
  defineProps<{
    eventId: string
    embedded?: boolean
    sandbox?: boolean
    /** The plan to open first (the one the map was showing), if it exists. */
    initialPlanId?: string | null
  }>(),
  { embedded: false, sandbox: false, initialPlanId: null },
)

const emit = defineEmits<{
  /** Something was saved: plans, pins, drawings or a picture. */
  changed: []
  /** The plan being edited changed (picked, created or deleted). */
  'plan-change': [planId: string | null]
}>()

const { t } = useI18n()
const { get, post, put, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()
const authStore = useAuthStore()

const { locations } = useLocations(() => props.eventId)

// ── Plans ─────────────────────────────────────────────────────────────────
const plans = ref<VenuePlanRead[]>([])
const loading = ref(true)
// A failed load is not "no plans": showing the empty state would invite an
// admin to add the plans they already have again.
const loadError = ref(false)
const selectedPlanId = ref<string | null>(null)
const plan = computed(() => plans.value.find((p) => p.id === selectedPlanId.value) ?? null)
watch(selectedPlanId, (id) => emit('plan-change', id))
const planIndex = computed(() => plans.value.findIndex((p) => p.id === selectedPlanId.value))

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const res = await get<{ data: VenueMapRead }>({
      url: `/events/${props.eventId}/venue-map`,
    })
    plans.value = res.data.plans
    if (!plans.value.some((p) => p.id === selectedPlanId.value)) {
      const initial = plans.value.find((p) => p.id === props.initialPlanId)
      selectedPlanId.value = (initial ?? plans.value[0])?.id ?? null
    }
  } catch (error) {
    plans.value = []
    selectedPlanId.value = null
    loadError.value = true
    toastApiError(error)
  } finally {
    loading.value = false
    resetHistory()
  }
}

watch(() => props.eventId, load, { immediate: true })

/**
 * The nav shows "Map" only while the event has a plan with a picture or a
 * drawing (`venue_plan_count`), so refresh the selected event after anything
 * that can change that count. The store ignores any event other than the
 * selected one.
 */
function refreshEventCounts() {
  return authStore.refreshSelectedEvent(props.eventId)
}

function replacePlan(updated: VenuePlanRead) {
  const index = plans.value.findIndex((p) => p.id === updated.id)
  if (index >= 0) plans.value[index] = updated
}

/** Switch plans only once every drawing step of the current one is saved. */
async function selectPlan(id: string | null) {
  if (id === selectedPlanId.value) return
  editor.flushNudge()
  await history.flush()
  selectedPlanId.value = id
}

const planModel = computed({
  get: () => selectedPlanId.value,
  set: (id: string | null) => void selectPlan(id),
})

// "Add map": name, and blank canvas or picture.
const createOpen = ref(false)
const createDialog = ref<InstanceType<typeof VenuePlanCreateDialog> | null>(null)
const creating = ref(false)
/** Plans created with "Use a picture": the side panel offers the upload big. */
const wantsPicture = ref(new Set<string>())

function openCreate() {
  createOpen.value = true
}

async function createPlan(value: PlanCreateValue) {
  if (creating.value) return
  creating.value = true
  const fromTemplate = value.mode === 'template' && !!value.templateId
  try {
    const res = await post<{ data: VenuePlanRead }>({
      url: `/events/${props.eventId}/venue-plans`,
      // A template brings its own canvas.
      body: fromTemplate
        ? { name: value.name, template_id: value.templateId }
        : { name: value.name, canvas: value.canvas },
    })
    plans.value.push(res.data)
    if (value.mode === 'picture') wantsPicture.value.add(res.data.id)
    await selectPlan(res.data.id)
    createOpen.value = false
    emit('changed')
    if (fromTemplate) {
      // The drawing is there already; what is left is placing the pins.
      toast.success(t('mapEditor.templates.createdFrom'))
      void refreshEventCounts()
    } else {
      toast.success(t('mapEditor.plans.created'))
    }
    // A blank plan opens ready to draw.
    if (value.mode === 'blank') editor.setTool('rect')
  } catch (error) {
    const { code } = toastApiError(error)
    if (fromTemplate && value.templateId && code === 'venue_template.not_found') {
      createDialog.value?.templateGone(value.templateId)
    }
  } finally {
    creating.value = false
  }
}

// Rename dialog.
const renameDialog = ref<{ open: boolean; name: string }>({ open: false, name: '' })
const savingName = ref(false)
const trimmedName = computed(() => renameDialog.value.name.trim())

function openRename() {
  if (!plan.value) return
  renameDialog.value = { open: true, name: plan.value.name }
}

async function submitRename() {
  const name = trimmedName.value
  if (!name || savingName.value || !plan.value) return
  savingName.value = true
  try {
    const res = await patch<{ data: VenuePlanRead }>({
      url: `/venue-plans/${plan.value.id}`,
      body: { name },
    })
    replacePlan(res.data)
    emit('changed')
    toast.success(t('mapEditor.plans.saved'))
    renameDialog.value.open = false
  } catch (error) {
    toastApiError(error)
  } finally {
    savingName.value = false
  }
}

// "Save as template…": a copy of this plan's drawing and picture (no pins,
// no place links) in my own templates, to start plans from in any event.
const saveTemplateOpen = ref(false)
const savingTemplate = ref(false)

function openSaveTemplate() {
  if (plan.value) saveTemplateOpen.value = true
}

async function submitSaveTemplate(name: string) {
  const current = plan.value
  if (!current || savingTemplate.value) return
  savingTemplate.value = true
  try {
    // The template is copied from what the server holds: save every step first.
    editor.flushNudge()
    await history.flush()
    await post<{ data: VenueTemplateRead }>({
      url: `/venue-plans/${current.id}/save-as-template`,
      body: { name },
    })
    toast.success(t('mapEditor.templates.saved'))
    saveTemplateOpen.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    savingTemplate.value = false
  }
}

async function deletePlan() {
  const current = plan.value
  if (!current) return
  const confirmed = await confirmDestructive({
    text: t('mapEditor.plans.deleteConfirm', { name: current.name }),
    confirmText: t('common.actions.delete'),
  })
  if (!confirmed) return
  try {
    await history.flush()
    await del({ url: `/venue-plans/${current.id}` })
    const index = plans.value.findIndex((p) => p.id === current.id)
    plans.value = plans.value.filter((p) => p.id !== current.id)
    selectedPlanId.value = plans.value[Math.min(index, plans.value.length - 1)]?.id ?? null
    toast.success(t('mapEditor.plans.deleted'))
    emit('changed')
    void refreshEventCounts()
  } catch (error) {
    toastApiError(error)
  }
}

async function movePlan(offset: -1 | 1) {
  const from = planIndex.value
  const to = from + offset
  if (from < 0 || to < 0 || to >= plans.value.length) return
  const ids = plans.value.map((p) => p.id)
  ;[ids[from], ids[to]] = [ids[to]!, ids[from]!]
  try {
    const res = await put<{ data: VenuePlanRead[] }>({
      url: `/events/${props.eventId}/venue-plans/order`,
      body: { plan_ids: ids },
    })
    // The order endpoint answers with plans as stored; keep the drawings we
    // already hold (they may be newer than a concurrent answer).
    plans.value = res.data.map((p) => {
      const known = plans.value.find((q) => q.id === p.id)
      return known ? { ...p, shapes: known.shapes, shapes_revision: known.shapes_revision } : p
    })
    emit('changed')
  } catch (error) {
    toastApiError(error)
  }
}

function onUploaded(updated: VenuePlanRead) {
  replacePlan(updated)
  wantsPicture.value.delete(updated.id)
  emit('changed')
  void refreshEventCounts()
}

async function removePicture() {
  const current = plan.value
  if (!current?.image_etag) return
  const confirmed = await confirmDestructive({
    text: t('mapEditor.picture.removeConfirm', { name: current.name }),
    confirmText: t('mapEditor.picture.remove'),
  })
  if (!confirmed) return
  try {
    const res = await del<{ data: VenuePlanRead }>({ url: `/venue-plans/${current.id}/image` })
    replacePlan(res.data)
    toast.success(t('mapEditor.picture.removed'))
    emit('changed')
    void refreshEventCounts()
  } catch (error) {
    toastApiError(error)
  }
}

// ── Drawing history ───────────────────────────────────────────────────────
const history = useShapeHistory({
  send: async (planId, ops, expectedRevision) => {
    const res = await post<{ data: VenuePlanShapesRead }>({
      url: `/venue-plans/${planId}/shapes/batch`,
      body: { ops, expected_revision: expectedRevision },
    })
    return res.data
  },
  onConflict: async () => {
    toast.info(t('mapEditor.draw.conflict'))
    await load()
  },
  onError: (error) => toastApiError(error),
  onSaved: (result, previous) => {
    const saved = plans.value.find((p) => p.id === result.plan_id)
    if (saved) {
      saved.shapes = result.shapes
      saved.shapes_revision = result.revision
    }
    invalidatePlanShapes(result.plan_id)
    emit('changed')
    // Drawing the first shape (or deleting the last) can show or hide the map.
    if (previous.length > 0 !== result.shapes.length > 0) void refreshEventCounts()
  },
})

function resetHistory() {
  const current = plan.value
  history.reset(
    current?.id ?? null,
    sortShapes(current?.shapes ?? []),
    current?.shapes_revision ?? 0,
  )
}

// Leaving with unsaved drawing steps: let the browser ask first.
useEventListener(window, 'beforeunload', (event: BeforeUnloadEvent) => {
  if (history.pending.value === 0) return
  event.preventDefault()
  event.returnValue = ''
})

// ── Canvas ────────────────────────────────────────────────────────────────
const size = computed(() => (plan.value ? planSize(plan.value) : { W: 0, H: 0 }))
const width = computed(() => size.value.W)
const height = computed(() => size.value.H)

const rootRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const canvasRef = ref<HTMLElement | null>(null)
const inspectorRef = ref<InstanceType<typeof VenueShapeInspector> | null>(null)

/** What a press on the canvas landed on: a handle, a shape, or the ground. */
function pressTarget(event: Event): PressTarget {
  const el = event.target as Element | null
  if (!el || typeof el.closest !== 'function') return null
  const handle = el.closest('[data-handle]')?.getAttribute('data-handle')
  if (handle) {
    const [kind, arg] = handle.split(':')
    if (kind === 'vertex') return { type: 'handle', handle: { kind, index: Number(arg) } }
    if (kind === 'insert') return { type: 'handle', handle: { kind, edgeIndex: Number(arg) } }
    if (kind === 'resize' && RECT_HANDLES.includes(arg as RectHandle)) {
      return { type: 'handle', handle: { kind, handle: arg as RectHandle } }
    }
    if (kind === 'rotate' || kind === 'scale') return { type: 'handle', handle: { kind } }
    return { type: 'handle', handle: { kind: 'label' } }
  }
  const id = el.closest('[data-shape-id]')?.getAttribute('data-shape-id')
  return id ? { type: 'shape', id } : null
}

const panZoom = usePanZoom(svgRef, {
  width,
  height,
  // While placing a pin the plan pans as before; otherwise the tool decides.
  panFilter: (e) =>
    placing.value
      ? e.pointerType !== 'mouse' || e.button === 0
      : editor.panFilter(e, pressTarget(e)),
  dblclickZoom: () => editor.tool.value === 'select',
})
const { viewBoxAttr, unitsPerPixel, isGesturing } = panZoom

const editor = useShapeEditor({
  shapes: () => history.shapes.value,
  size: () => size.value,
  upp: () => unitsPerPixel.value,
  toPoint: (x, y) => {
    const p = panZoom.clientToSvg(x, y)
    return [width.value > 0 ? p.x / width.value : 0, height.value > 0 ? p.y / height.value : 0]
  },
  execute: (command) => history.execute(command),
  undo: () => history.undo(),
  redo: () => history.redo(),
  // The inspector mounts with the label draft, so focus it after the render.
  onLabelDraft: () => void nextTick(() => inspectorRef.value?.focusLabel()),
})
const {
  tool,
  selected: selectedShape,
  selectedId: selectedShapeId,
  selectedVertex,
  draft,
  snapEnabled,
  snapHit,
  spaceHeld,
  displayShapes,
  grid,
  activeProp,
  propHover,
} = editor

// Two fingers on the plan: whatever one finger started is a pinch now.
watch(panZoom.pointerCount, (n) => {
  if (n > 1) editor.abortGesture()
})

const {
  src,
  loading: imageLoading,
  error: imageError,
} = useAuthedImage(() => planImageUrl(plan.value))

const hasImage = computed(() => !!plan.value?.image_etag)
const isBlankAndEmpty = computed(
  () => !!plan.value && !hasImage.value && history.shapes.value.length === 0,
)

const markers = computed<VenueMarkerRead[]>(() => plan.value?.markers ?? [])
const locationNames = computed(() => new Map(locations.value.map((l) => [l.id, l.name])))
const locationNameRecord = computed(() => Object.fromEntries(locationNames.value))
const placedLocationIds = computed(() =>
  markers.value.flatMap((m) => (m.location_id ? [m.location_id] : [])),
)

/** A location pin whose place still exists is drawn as a pill, like on the map. */
function isPill(marker: VenueMarkerRead) {
  return !!marker.location_id && locationNames.value.has(marker.location_id)
}

function markerName(marker: VenueMarkerRead): string {
  const name = marker.location_id ? locationNames.value.get(marker.location_id) : null
  if (name) return name
  const kind = t(markerKindLabelKey(marker.kind))
  return marker.label ? `${marker.label} (${kind})` : kind
}

/** The Deko tool's ghost: the decoration a tap would place, under the pointer. */
const propGhost = computed(() =>
  tool.value === 'prop' && propHover.value
    ? {
        prop: activeProp.value,
        at: propHover.value,
        scale: editor.lastPropScale.value[activeProp.value] ?? 1,
      }
    : null,
)

const lineDraft = computed(() => {
  const d = draft.value
  return d && (d.tool === 'polygon' || d.tool === 'path') ? d : null
})

const toolHint = computed(() => {
  if (lineDraft.value || draft.value?.tool === 'label') return null
  if (tool.value === 'rect') {
    return isBlankAndEmpty.value ? t('mapEditor.draw.emptyHint') : t('mapEditor.draw.rectHint')
  }
  if (tool.value === 'polygon') return t('mapEditor.draw.polygonHint')
  if (tool.value === 'path') return t('mapEditor.draw.pathHint')
  if (tool.value === 'label') return t('mapEditor.draw.labelHint')
  if (tool.value === 'prop') {
    return t('mapEditor.draw.propHint', { name: t(propLabelKey(activeProp.value)) })
  }
  return isBlankAndEmpty.value ? t('mapEditor.draw.emptyHint') : null
})

const canvasCursor = computed(() => {
  if (placing.value) return 'cursor-crosshair'
  if (spaceHeld.value) return 'cursor-grab active:cursor-grabbing'
  if (tool.value !== 'select') return 'cursor-crosshair'
  return 'cursor-grab active:cursor-grabbing'
})

/**
 * Set when a pointer-up ends an edit drag, so the click the browser fires
 * right after it is not read as "clicked the empty plan". Dragging the "+"
 * on an edge replaces that handle with a vertex mid-drag, so the click lands
 * on the plan itself and would otherwise clear the selection.
 */
let swallowClick = false

function onSvgPointerDown(event: PointerEvent) {
  swallowClick = false
  if (placing.value) return
  editor.onPointerDown(event, pressTarget(event))
}

/**
 * A shape asks to be selected (a click on it, or Enter). With a drawing tool
 * the press already did what the tool does — placed a tree on a room, added a
 * corner on it — so its click must not select the room instead.
 */
function onSelectShape(shape: { id: string }, event: MouseEvent | KeyboardEvent) {
  if (event instanceof MouseEvent && tool.value !== 'select') return
  // Placing a pin: the tap is for the pin (the plan's click handler), not the shape.
  if (event instanceof MouseEvent && placing.value) return
  editor.select(shape.id)
}

function onSvgDoubleClick(event: MouseEvent) {
  if (editor.onDoubleClick()) event.preventDefault()
}

useEventListener(window, 'pointermove', (e: PointerEvent) => editor.onPointerMove(e))
useEventListener(window, 'pointerup', (e: PointerEvent) => {
  // Also after Escape cancelled the drag mid-press: that release is no click on the plan.
  if (editor.dragging.value || editor.pressWasCancelled()) swallowClick = true
  editor.onPointerUp(e)
})
useEventListener(window, 'pointercancel', (e: PointerEvent) => editor.onPointerCancel(e))
useEventListener(window, 'blur', () => editor.onBlur())

// One selection at a time: a pin or a drawing.
watch(selectedShapeId, (id) => {
  if (id) selectedMarkerId.value = null
})

// A drawing tool and pin placement exclude each other.
watch(tool, (next) => {
  if (next !== 'select') placing.value = null
})

// ── Placement ─────────────────────────────────────────────────────────────
type Placing = { key: string; kind: MarkerKind; locationId: string | null; name: string }
const placing = ref<Placing | null>(null)
const creatingMarker = ref(false)

function startPlacing(next: Placing) {
  editor.setTool('select')
  placing.value = placing.value?.key === next.key ? null : next
  selectedMarkerId.value = null
  editor.select(null)
  // On a phone the sheet covers the plan the pin goes on: out of the way.
  sheetOpen.value = false
  // On a phone the palette sits below the map; bring the map back into view.
  if (placing.value) {
    void nextTick(() => canvasRef.value?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }))
  }
}

function pickLocation(location: LocationRead) {
  startPlacing({
    key: `location:${location.id}`,
    kind: 'location',
    locationId: location.id,
    name: location.name,
  })
}

function pickKind(kind: Exclude<MarkerKind, 'location'>) {
  startPlacing({ key: `kind:${kind}`, kind, locationId: null, name: t(markerKindLabelKey(kind)) })
}

/** Focus an element of this editor after the next render (it may not exist yet). */
function focusLater(selector: string) {
  void nextTick(() =>
    rootRef.value
      ?.querySelector<HTMLElement | SVGElement>(selector)
      ?.focus({ preventScroll: true }),
  )
}

function cancelPlacing() {
  const item = placing.value
  placing.value = null
  // The banner and its focused button are gone; go back to where placement began.
  if (item) focusLater(`[data-testid="palette-${item.key.replace(':', '-')}"]`)
}

async function placeAt(point: Point) {
  const item = placing.value
  const current = plan.value
  if (!item || !current || creatingMarker.value) return
  creatingMarker.value = true
  try {
    const res = await post<{ data: VenueMarkerRead }>({
      url: `/venue-plans/${current.id}/markers`,
      body: { kind: item.kind, location_id: item.locationId, x: point.x, y: point.y },
    })
    ;(current.markers ??= []).push(res.data)
    emit('changed')
    placing.value = null
    // Selected for the arrow keys; the phone sheet stays shut for the next pin.
    quietSelection = true
    selectedMarkerId.value = res.data.id
    // Focus the new pin, so the arrow keys nudge it straight away; the banner
    // that held focus has just gone.
    focusLater(`[data-testid="map-marker-${res.data.location_id ?? res.data.id}"]`)
    toast.success(t('mapEditor.place.added'))
  } catch (error) {
    toastApiError(error)
  } finally {
    creatingMarker.value = false
  }
}

/** A click (or tap) on the plan, not on a pin: place a pin, or clear the selection. */
function onCanvasClick(event: MouseEvent) {
  // The click that ends a pan is neither a placement nor a deselect.
  if (isGesturing.value) return
  if (swallowClick) {
    swallowClick = false
    return
  }
  if (!placing.value) {
    // A tap on the plan puts the phone sheet away (a selection also closes it).
    if (!hasSelection.value) sheetOpen.value = false
    selectedMarkerId.value = null
    if (tool.value === 'select' && pressTarget(event) === null) editor.select(null)
    return
  }
  const point = panZoom.clientToSvg(event.clientX, event.clientY)
  if (point.x < 0 || point.y < 0 || point.x > width.value || point.y > height.value) return
  void placeAt(toNormalised(point, width.value, height.value))
}

/** Keyboard (and imprecise fingers): place in the middle of the view, then nudge. */
function placeInCentre() {
  const vb = panZoom.viewBox.value
  void placeAt(toNormalised({ x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 }, width.value, height.value))
}

const OVERLAY_SELECTOR = '[role="dialog"], [role="alertdialog"], [role="listbox"], [role="menu"]'

/**
 * Drawing shortcuts belong to the editor: they fire when focus is inside it or
 * nowhere in particular (the body, after a click on the plan), never from the
 * rest of the page and never while a dialog or menu is open on top of it.
 */
function keyIsForEditor(event: KeyboardEvent): boolean {
  if (document.querySelector(`[role="dialog"][data-state="open"], [role="alertdialog"]`)) {
    return false
  }
  const target = event.target
  if (!(target instanceof Element)) return true
  if (target.closest(OVERLAY_SELECTOR)) return false
  if (target === document.body || target === document.documentElement) return true
  return !!rootRef.value?.contains(target)
}

useEventListener(document, 'keydown', (event: KeyboardEvent) => {
  if (!keyIsForEditor(event)) return
  if (event.key === 'Escape' && placing.value) {
    cancelPlacing()
    return
  }
  if (!plan.value) return
  editor.onKeyDown(event)
})
useEventListener(document, 'keyup', (event: KeyboardEvent) => editor.onKeyUp(event))

// ── Selected pin ──────────────────────────────────────────────────────────
const selectedMarkerId = ref<string | null>(null)
const selectedMarker = computed(
  () => markers.value.find((m) => m.id === selectedMarkerId.value) ?? null,
)
const labelDraft = ref('')

watch(selectedMarker, (marker) => {
  labelDraft.value = marker?.label ?? ''
  if (marker) editor.select(null)
})

watch(selectedPlanId, () => {
  placing.value = null
  selectedMarkerId.value = null
  editor.select(null)
  editor.cancelDraft()
  panZoom.reset()
  resetHistory()
})

/** PATCH a pin; on failure put back what `revert` restores and say why. */
async function patchMarker(
  marker: VenueMarkerRead,
  body: Partial<Pick<VenueMarkerRead, 'kind' | 'label' | 'x' | 'y'>>,
  revert: () => void,
) {
  try {
    const res = await patch<{ data: VenueMarkerRead }>({
      url: `/venue-markers/${marker.id}`,
      body,
    })
    marker.kind = res.data.kind
    marker.label = res.data.label
    emit('changed')
  } catch (error) {
    revert()
    toastApiError(error)
  }
}

function saveLabel() {
  const marker = selectedMarker.value
  if (!marker || marker.kind === 'location') return
  const label = labelDraft.value.trim() || null
  if (label === (marker.label ?? null)) return
  const previous = marker.label ?? null
  marker.label = label
  void patchMarker(marker, { label }, () => {
    marker.label = previous
    labelDraft.value = previous ?? ''
  })
}

function onKindChange(event: Event) {
  const marker = selectedMarker.value
  if (!marker || marker.kind === 'location') return
  const kind = (event.target as HTMLSelectElement).value as MarkerKind
  if (kind === marker.kind) return
  const previous = marker.kind
  marker.kind = kind
  void patchMarker(marker, { kind }, () => (marker.kind = previous))
}

async function deleteMarker(marker: VenueMarkerRead) {
  const confirmed = await confirmDestructive({
    text: t('mapEditor.marker.deleteConfirm', { name: markerName(marker) }),
    confirmText: t('common.actions.delete'),
  })
  if (!confirmed) return
  const current = plan.value
  try {
    await del({ url: `/venue-markers/${marker.id}` })
    if (current?.markers) current.markers = current.markers.filter((m) => m.id !== marker.id)
    if (selectedMarkerId.value === marker.id) selectedMarkerId.value = null
    emit('changed')
  } catch (error) {
    toastApiError(error)
  }
}

// ── Dragging a pin ────────────────────────────────────────────────────────
/** Movement (CSS px) before a press on a pin becomes a drag. */
const DRAG_THRESHOLD = 4
let drag: {
  marker: VenueMarkerRead
  pointerId: number
  start: Point
  origin: Point
  /** Pointer minus pin, in image units: a pill is grabbed above its point. */
  grab: Point
  moved: boolean
} | null = null
const draggingId = ref<string | null>(null)

function onMarkerPointerDown(event: PointerEvent, marker: VenueMarkerRead) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  // Keep the plan from panning underneath.
  event.stopPropagation()
  selectedMarkerId.value = marker.id
  try {
    ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
  } catch {
    // Pointer already gone; the drag simply does not start.
  }
  const pressed = panZoom.clientToSvg(event.clientX, event.clientY)
  drag = {
    marker,
    pointerId: event.pointerId,
    start: { x: event.clientX, y: event.clientY },
    origin: { x: marker.x, y: marker.y },
    grab: { x: pressed.x - marker.x * width.value, y: pressed.y - marker.y * height.value },
    moved: false,
  }
}

function onMarkerPointerMove(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  event.stopPropagation()
  if (!drag.moved) {
    const distance = Math.hypot(event.clientX - drag.start.x, event.clientY - drag.start.y)
    if (distance <= DRAG_THRESHOLD) return
    drag.moved = true
    draggingId.value = drag.marker.id
  }
  const pointer = panZoom.clientToSvg(event.clientX, event.clientY)
  const point = toNormalised(
    { x: pointer.x - drag.grab.x, y: pointer.y - drag.grab.y },
    width.value,
    height.value,
  )
  drag.marker.x = point.x
  drag.marker.y = point.y
}

function onMarkerPointerUp(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  event.stopPropagation()
  const { marker, origin, moved } = drag
  drag = null
  draggingId.value = null
  if (!moved) return
  if (event.type === 'pointercancel') {
    marker.x = origin.x
    marker.y = origin.y
    return
  }
  void patchMarker(marker, { x: marker.x, y: marker.y }, () => {
    marker.x = origin.x
    marker.y = origin.y
  })
}

// ── Phone sheet ───────────────────────────────────────────────────────────
/**
 * Below `lg` the side panel is a bottom sheet over the plan. It is shut by
 * default, so the plan has the whole height, and opens with the "Pins &
 * picture" button on the plan, or on its own when a shape or pin is tapped
 * with the select tool, or a text is started. A drag selects without opening
 * it, and so does a freshly drawn shape or placed pin (the next one is drawn
 * or placed on the plan). On a wide screen it is a plain side panel and
 * `sheetOpen` changes nothing.
 */
const sheetOpen = ref(false)
const hasSelection = computed(
  () => !!selectedShape.value || !!selectedMarker.value || draft.value?.tool === 'label',
)
/** A pointer is down: wait for it to come up, since a drag must not open the sheet. */
let pressing = false
let openAfterPress = false
/** The next selection is the editor's own (a pin just placed), not a tap. */
let quietSelection = false

watch(
  () => [selectedShapeId.value, selectedMarkerId.value, draft.value?.tool === 'label'] as const,
  ([shapeId, markerId, label], [prevShape, prevMarker, prevLabel]) => {
    const picked =
      (!!shapeId && shapeId !== prevShape && tool.value === 'select') ||
      (!!markerId && markerId !== prevMarker)
    const quiet = quietSelection
    quietSelection = false
    // A decoration is turned and sized with its grips on the plan, which the
    // sheet would cover; its details stay one tap away on the "Selection" button.
    const decoration = !!shapeId && selectedShape.value?.kind === 'prop'
    if (label && !prevLabel) sheetOpen.value = true
    else if (!picked || quiet || decoration) return
    else if (pressing) openAfterPress = true
    else sheetOpen.value = true
  },
)

// Another tool: the plan (and the Deko strip) need the room.
watch(tool, () => {
  sheetOpen.value = false
})

// Nothing selected any more: the sheet showed only that, so it goes too.
watch(hasSelection, (has) => {
  if (!has) sheetOpen.value = false
})

useEventListener(
  window,
  'pointerdown',
  () => {
    pressing = true
    openAfterPress = false
  },
  { capture: true },
)
useEventListener(
  window,
  'pointerup',
  () => {
    const dragged = editor.dragging.value || !!drag?.moved
    pressing = false
    if (openAfterPress && !dragged && hasSelection.value) sheetOpen.value = true
    openAfterPress = false
  },
  { capture: true },
)
useEventListener(
  window,
  'pointercancel',
  () => {
    pressing = false
    openAfterPress = false
  },
  { capture: true },
)

const sheetTitle = computed(() =>
  hasSelection.value ? t('mapEditor.sheet.selection') : t('mapEditor.sheet.pins'),
)

/** The "Pins & picture" button on the plan; the drawing hints and bars take the bottom otherwise. */
const showSheetButton = computed(
  () => !sheetOpen.value && !placing.value && !lineDraft.value && tool.value !== 'prop',
)

// ── Keyboard (pins) ───────────────────────────────────────────────────────
const NUDGE = 0.005
const NUDGE_LARGE = 0.02
const NUDGE_SAVE_DELAY = 400
// A burst of arrow presses is one PATCH; the origin is where the burst began.
const nudgeTimers = new Map<string, ReturnType<typeof setTimeout>>()
const nudgeOrigins = new Map<string, { marker: VenueMarkerRead; origin: Point }>()

function flushNudge(id: string) {
  clearTimeout(nudgeTimers.get(id))
  nudgeTimers.delete(id)
  const pending = nudgeOrigins.get(id)
  if (!pending) return
  nudgeOrigins.delete(id)
  const { marker, origin } = pending
  void patchMarker(marker, { x: marker.x, y: marker.y }, () => {
    marker.x = origin.x
    marker.y = origin.y
  })
}

function nudge(marker: VenueMarkerRead, dx: number, dy: number) {
  if (!nudgeOrigins.has(marker.id)) {
    nudgeOrigins.set(marker.id, { marker, origin: { x: marker.x, y: marker.y } })
  }
  marker.x = clamp01(marker.x + dx)
  marker.y = clamp01(marker.y + dy)
  clearTimeout(nudgeTimers.get(marker.id))
  nudgeTimers.set(
    marker.id,
    setTimeout(() => flushNudge(marker.id), NUDGE_SAVE_DELAY),
  )
}

const ARROWS: Record<string, Point> = {
  ArrowLeft: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
  ArrowUp: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 },
}

// The pin's own keys are prevented, so the drawing shortcuts on the document skip them.
function onMarkerKey(event: KeyboardEvent, marker: VenueMarkerRead) {
  const arrow = ARROWS[event.key]
  if (arrow) {
    event.preventDefault()
    const step = event.shiftKey ? NUDGE_LARGE : NUDGE
    nudge(marker, arrow.x * step, arrow.y * step)
    return
  }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    void deleteMarker(marker)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    selectedMarkerId.value = marker.id
  } else if (event.key === 'Escape') {
    event.preventDefault()
    selectedMarkerId.value = null
  }
}

// Don't lose a nudge that is still waiting for its debounce.
onBeforeUnmount(() => {
  for (const id of [...nudgeTimers.keys()]) flushNudge(id)
  editor.flushNudge()
})

// The menu trigger sits inside a HintTooltip, so it anchors to the tooltip,
// not to its own menu: the menu content is told where the button is, or it
// opens off-screen (reka-ui finds an anchor through the nearest popup root).
const planActionsButton = useTemplateRef<ComponentPublicInstance>('planActionsButton')
</script>

<template>
  <div
    ref="rootRef"
    :class="embedded ? 'flex h-full min-h-0 flex-col gap-3' : 'space-y-4'"
    data-testid="venue-map-editor"
  >
    <div v-if="!embedded" class="space-y-1">
      <h2 class="text-lg font-semibold">{{ t('mapEditor.settings.title') }}</h2>
      <p class="text-muted-foreground text-sm">{{ t('mapEditor.settings.description') }}</p>
    </div>

    <!-- Plans and what to do with them; on the map page also "Done". -->
    <div
      v-if="embedded || (!loading && !loadError && plans.length > 0)"
      class="flex min-w-0 items-center gap-2"
    >
      <VenuePlanSwitcher
        v-if="!loading && !loadError && plans.length > 0"
        v-model="planModel"
        :plans="plans"
        compact
        class="min-w-0 flex-1"
      >
        <template #trailing>
          <DropdownMenu v-if="plan">
            <HintTooltip :label="t('mapEditor.plans.actions')">
              <DropdownMenuTrigger as-child>
                <Button
                  ref="planActionsButton"
                  variant="outline"
                  size="icon-sm"
                  class="max-lg:size-9"
                  :aria-label="t('mapEditor.plans.actions')"
                  data-testid="plan-actions"
                >
                  <EllipsisVertical />
                </Button>
              </DropdownMenuTrigger>
            </HintTooltip>
            <DropdownMenuContent align="end" :reference="planActionsButton?.$el">
              <DropdownMenuItem data-testid="plan-rename" @select="openRename">
                <Pencil />
                {{ t('mapEditor.plans.rename') }}
              </DropdownMenuItem>
              <DropdownMenuItem
                :disabled="!hasImage && history.shapes.value.length === 0"
                data-testid="plan-save-template"
                @select="openSaveTemplate"
              >
                <LayoutTemplate />
                {{ t('mapEditor.templates.save') }}
              </DropdownMenuItem>
              <template v-if="plans.length > 1">
                <DropdownMenuItem
                  :disabled="planIndex <= 0"
                  data-testid="plan-move-up"
                  @select="movePlan(-1)"
                >
                  <ArrowLeft />
                  {{ t('mapEditor.plans.moveUp') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  :disabled="planIndex >= plans.length - 1"
                  data-testid="plan-move-down"
                  @select="movePlan(1)"
                >
                  <ArrowRight />
                  {{ t('mapEditor.plans.moveDown') }}
                </DropdownMenuItem>
              </template>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                data-testid="plan-delete"
                @select="deletePlan"
              >
                <Trash2 />
                {{ t('mapEditor.plans.delete') }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="sm"
            class="max-lg:size-9 max-lg:px-0"
            :aria-label="t('mapEditor.plans.add')"
            data-testid="plan-add"
            @click="openCreate"
          >
            <Plus />
            <span class="hidden sm:inline">{{ t('mapEditor.plans.add') }}</span>
          </Button>
        </template>
      </VenuePlanSwitcher>
      <p v-else class="min-w-0 flex-1 truncate text-sm font-medium">
        {{ t('mapEditor.settings.title') }}
      </p>
      <slot name="actions" />
    </div>

    <Skeleton v-if="loading" :class="embedded ? 'min-h-0 w-full flex-1' : 'h-80 w-full'" />

    <div
      v-else-if="loadError"
      class="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center"
      role="alert"
      data-testid="map-editor-error"
    >
      <p class="text-muted-foreground text-sm">{{ t('mapEditor.plans.loadError') }}</p>
      <Button variant="outline" data-testid="map-editor-retry" @click="load">
        {{ t('venueMap.view.retry') }}
      </Button>
    </div>

    <div
      v-else-if="plans.length === 0"
      class="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center"
      data-testid="map-editor-empty"
    >
      <MapIcon class="text-muted-foreground size-10" aria-hidden="true" />
      <div class="space-y-1">
        <p class="font-medium">{{ t('mapEditor.plans.empty') }}</p>
        <p class="text-muted-foreground max-w-md text-sm">{{ t('mapEditor.plans.emptyHint') }}</p>
      </div>
      <Button data-testid="plan-add" @click="openCreate">
        <Plus />
        {{ t('mapEditor.plans.add') }}
      </Button>
    </div>

    <div
      v-else-if="plan"
      class="relative grid gap-4"
      :class="
        embedded
          ? 'min-h-0 flex-1 grid-rows-[minmax(0,1fr)] gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]'
          : 'lg:grid-cols-[minmax(0,1fr)_18rem]'
      "
    >
      <div class="flex min-h-0 min-w-0 flex-col gap-2">
        <!-- On a phone the tools go under the plan, in thumb reach. -->
        <VenueEditorToolbar
          class="max-lg:order-last"
          :tool="tool"
          :snap-enabled="snapEnabled"
          :can-undo="history.canUndo.value"
          :can-redo="history.canRedo.value"
          :pending="history.pending.value"
          @set-tool="editor.setTool"
          @toggle-snap="editor.toggleSnap"
          @undo="editor.undo"
          @redo="editor.redo"
        />

        <div
          ref="canvasRef"
          class="map-ground relative scroll-mt-20 overflow-hidden rounded-lg border px-4 pt-10 pb-4"
          :class="[embedded ? 'min-h-0 flex-1' : 'h-[60dvh] min-h-72', planSurfaceClass(plan)]"
        >
          <!-- Padding plus `overflow-visible`: a pin on the plan's edge stays whole. -->
          <svg
            ref="svgRef"
            :viewBox="viewBoxAttr"
            class="block h-full w-full touch-none overflow-visible select-none"
            :class="canvasCursor"
            role="group"
            :aria-label="plan.name"
            aria-describedby="map-editor-shortcuts"
            :aria-busy="imageLoading || undefined"
            :data-tool="tool"
            data-testid="editor-canvas"
            @pointerdown="onSvgPointerDown"
            @pointerleave="editor.onPointerLeave()"
            @dblclick="onSvgDoubleClick"
            @click="onCanvasClick"
          >
            <image
              v-if="hasImage && src"
              :href="src"
              x="0"
              y="0"
              :width="width"
              :height="height"
              preserveAspectRatio="none"
            />
            <rect
              x="0"
              y="0"
              :width="width"
              :height="height"
              :style="{
                fill: hasImage ? 'none' : 'var(--map-canvas)',
                stroke: 'var(--map-canvas-edge)',
              }"
              stroke-width="1"
              vector-effect="non-scaling-stroke"
              stroke-dasharray="6 4"
              pointer-events="none"
              data-testid="editor-canvas-bounds"
            />
            <VenueShapeLayer
              :shapes="displayShapes"
              :width="width"
              :height="height"
              :units-per-pixel="unitsPerPixel"
              interactive="all"
              :selected-shape-ids="selectedShapeId ? [selectedShapeId] : []"
              :location-names="locationNameRecord"
              @select-shape="onSelectShape"
            />
            <VenueDrawPreview
              :draft="draft"
              :snap-hit="snapHit"
              :width="width"
              :height="height"
              :units-per-pixel="unitsPerPixel"
              :grid="snapEnabled && tool !== 'select' && tool !== 'prop' ? grid : null"
              :prop-ghost="propGhost"
            />
            <g :class="tool !== 'select' ? 'pointer-events-none' : undefined">
              <template v-for="marker in markers" :key="marker.id">
                <component
                  :is="isPill(marker) ? VenueMarkerPill : VenueMarkerGlyph"
                  v-bind="
                    isPill(marker)
                      ? { name: markerName(marker) }
                      : { kind: marker.kind, label: markerName(marker) }
                  "
                  :x="marker.x * width"
                  :y="marker.y * height"
                  :scale="unitsPerPixel"
                  :selected="marker.id === selectedMarkerId"
                  role="button"
                  tabindex="0"
                  :aria-label="markerName(marker)"
                  :aria-pressed="marker.id === selectedMarkerId"
                  :aria-describedby="
                    marker.id === selectedMarkerId ? 'map-editor-nudge-hint' : undefined
                  "
                  :class="draggingId === marker.id ? 'cursor-grabbing' : 'cursor-move'"
                  :data-testid="`map-marker-${marker.location_id ?? marker.id}`"
                  @pointerdown="onMarkerPointerDown($event, marker)"
                  @pointermove="onMarkerPointerMove($event)"
                  @pointerup="onMarkerPointerUp($event)"
                  @pointercancel="onMarkerPointerUp($event)"
                  @click.stop
                  @dblclick.stop
                  @focus="selectedMarkerId = marker.id"
                  @keydown="onMarkerKey($event, marker)"
                />
              </template>
            </g>
            <VenueEditHandles
              v-if="
                selectedShape &&
                (tool === 'select' || (tool === 'prop' && selectedShape.kind === 'prop'))
              "
              :shape="selectedShape"
              :width="width"
              :height="height"
              :units-per-pixel="unitsPerPixel"
              :selected-vertex="selectedVertex"
              :active-grip="editor.activeGrip.value"
            />
          </svg>
          <VenuePinHint :container="svgRef" />

          <div v-if="hasImage && imageLoading" class="absolute inset-0" role="status">
            <Skeleton class="h-full w-full rounded-none" />
            <span class="sr-only">{{ t('venueMap.canvas.loading') }}</span>
          </div>
          <div
            v-else-if="hasImage && imageError"
            class="text-muted-foreground pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-sm"
            role="alert"
          >
            <ImageOff class="size-6" />
            {{ t('venueMap.canvas.error') }}
          </div>

          <div
            v-if="placing"
            class="bg-background/95 absolute inset-x-2 top-2 flex flex-wrap items-center gap-2 rounded-md border p-2 pl-3 text-sm shadow-md"
            role="status"
            data-testid="placement-banner"
          >
            <!-- Too narrow for text and buttons side by side: the buttons wrap below. -->
            <span class="min-w-0 grow basis-48">{{
              t('mapEditor.place.banner', { name: placing.name })
            }}</span>
            <Button
              size="sm"
              variant="secondary"
              class="ml-auto"
              :disabled="creatingMarker"
              data-testid="placement-centre"
              @click="placeInCentre"
            >
              {{ t('mapEditor.place.centre') }}
            </Button>
            <Button size="sm" variant="ghost" data-testid="placement-cancel" @click="cancelPlacing">
              <X />
              {{ t('mapEditor.place.cancel') }}
            </Button>
          </div>
          <p
            v-else-if="toolHint"
            class="bg-background/90 text-foreground pointer-events-none absolute inset-x-2 top-2 rounded-md border px-3 py-1.5 text-center text-[13px] shadow-sm"
            role="status"
            data-testid="draw-hint"
          >
            {{ toolHint }}
          </p>

          <!-- Finishing a shape or a line without a keyboard or a double tap. -->
          <div
            v-if="lineDraft"
            class="bg-background/95 absolute bottom-2 left-2 flex max-w-[calc(100%-4rem)] flex-wrap items-center gap-2 rounded-md border p-1.5 shadow-md"
            role="toolbar"
            :aria-label="t(`mapEditor.tools.${lineDraft.tool}`)"
            data-testid="draw-bar"
          >
            <Button
              size="sm"
              variant="ghost"
              :disabled="lineDraft.points.length === 0"
              data-testid="draw-undo-point"
              @click="editor.undoPoint()"
            >
              <Undo2 />
              {{ t('mapEditor.draw.undoPoint') }}
            </Button>
            <Button
              size="sm"
              :disabled="lineDraft.points.length < (lineDraft.tool === 'polygon' ? 3 : 2)"
              :data-testid="lineDraft.tool === 'polygon' ? 'draw-close' : 'draw-finish'"
              @click="editor.finishDraft()"
            >
              {{
                lineDraft.tool === 'polygon'
                  ? t('mapEditor.draw.closeShape')
                  : t('mapEditor.draw.finish')
              }}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              data-testid="draw-cancel"
              @click="editor.cancelDraft()"
            >
              <X />
              {{ t('mapEditor.draw.cancel') }}
            </Button>
          </div>

          <!-- The Deko tool's stamps; the zoom buttons keep their column on the right. -->
          <VenueDecorPalette
            v-if="tool === 'prop'"
            :model-value="activeProp"
            mode="stamp"
            class="absolute right-12 bottom-2 left-2 pointer-coarse:right-14"
            @update:model-value="editor.pickProp"
            @pick-line="editor.pickLinePreset"
            @pick-area="editor.pickAreaPreset"
          />

          <!-- Phones: the side panel is a sheet; this opens it. -->
          <Button
            v-if="showSheetButton"
            size="sm"
            variant="secondary"
            class="absolute bottom-2 left-2 h-10 max-w-[calc(100%-4.5rem)] border shadow-md lg:hidden"
            aria-controls="map-editor-panel"
            :aria-expanded="false"
            data-testid="editor-sheet-open"
            @click="sheetOpen = true"
          >
            <SlidersHorizontal v-if="hasSelection" />
            <MapPin v-else />
            <span class="truncate">{{ sheetTitle }}</span>
          </Button>

          <div class="absolute right-2 bottom-2 flex flex-col gap-1">
            <HintTooltip :label="t('venueMap.canvas.zoomIn')" side="left">
              <Button
                size="icon-sm"
                variant="secondary"
                class="shadow pointer-coarse:size-10"
                :aria-label="t('venueMap.canvas.zoomIn')"
                @click="panZoom.zoomIn()"
              >
                <Plus />
              </Button>
            </HintTooltip>
            <HintTooltip :label="t('venueMap.canvas.zoomOut')" side="left">
              <Button
                size="icon-sm"
                variant="secondary"
                class="shadow pointer-coarse:size-10"
                :aria-label="t('venueMap.canvas.zoomOut')"
                @click="panZoom.zoomOut()"
              >
                <Minus />
              </Button>
            </HintTooltip>
            <HintTooltip :label="t('venueMap.canvas.reset')" side="left">
              <Button
                size="icon-sm"
                variant="secondary"
                class="shadow pointer-coarse:size-10"
                :aria-label="t('venueMap.canvas.reset')"
                @click="panZoom.reset()"
              >
                <Maximize />
              </Button>
            </HintTooltip>
          </div>
        </div>
      </div>

      <!--
        Wide screens: the column beside the plan. Phones: a bottom sheet over
        the plan (and its tools), shut until asked for.
      -->
      <aside
        id="map-editor-panel"
        class="space-y-4 max-lg:absolute max-lg:inset-x-0 max-lg:bottom-0 max-lg:z-20 max-lg:max-h-[60%] max-lg:overflow-y-auto max-lg:overscroll-contain max-lg:rounded-t-xl max-lg:border max-lg:bg-background max-lg:px-3 max-lg:pb-3 max-lg:shadow-2xl"
        :class="[embedded ? 'min-h-0 overflow-y-auto pb-1' : '', sheetOpen ? '' : 'max-lg:hidden']"
        :aria-label="sheetTitle"
        data-testid="editor-panel"
      >
        <div
          class="bg-background sticky top-0 z-10 -mx-3 flex items-center gap-2 border-b px-3 py-1.5 lg:hidden"
        >
          <span
            class="bg-muted absolute top-1 left-1/2 h-1 w-10 -translate-x-1/2 rounded-full"
            aria-hidden="true"
          />
          <p class="min-w-0 flex-1 truncate pt-1 text-sm font-semibold">{{ sheetTitle }}</p>
          <HintTooltip :label="t('mapEditor.sheet.hide')">
            <Button
              size="icon"
              variant="ghost"
              class="mt-1"
              :aria-label="t('mapEditor.sheet.hide')"
              data-testid="editor-sheet-close"
              @click="sheetOpen = false"
            >
              <ChevronDown />
            </Button>
          </HintTooltip>
        </div>
        <VenueShapeInspector
          v-if="selectedShape || draft?.tool === 'label'"
          ref="inspectorRef"
          :shape="selectedShape"
          :label-draft="draft?.tool === 'label'"
          :locations="locations"
          :selected-vertex="selectedVertex"
          :width="width"
          :height="height"
          @update="(p) => editor.updateSelected(p)"
          @preview="(p) => editor.previewSelected(p)"
          @duplicate="editor.duplicateSelected()"
          @delete="editor.deleteSelected()"
          @reorder="(d) => editor.reorderSelected(d)"
          @remove-vertex="editor.removeSelectedVertex()"
          @commit-label="(text) => editor.commitLabel(text)"
          @cancel-label="editor.cancelDraft()"
          @close="editor.select(null)"
        />

        <section
          v-if="selectedMarker"
          class="space-y-3 rounded-lg border p-3"
          :aria-label="t('mapEditor.marker.title')"
          data-testid="marker-panel"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="text-muted-foreground text-xs">{{ t('mapEditor.marker.title') }}</p>
              <p class="truncate font-medium">{{ markerName(selectedMarker) }}</p>
            </div>
            <Button
              size="sm"
              variant="ghost"
              data-testid="marker-panel-close"
              @click="selectedMarkerId = null"
            >
              {{ t('mapEditor.marker.close') }}
            </Button>
          </div>

          <template v-if="selectedMarker.kind !== 'location'">
            <div class="space-y-1.5">
              <Label for="map-editor-marker-kind">{{ t('mapEditor.marker.kind') }}</Label>
              <NativeSelect
                id="map-editor-marker-kind"
                :model-value="selectedMarker.kind"
                class="w-full"
                data-testid="marker-kind"
                @change="onKindChange"
              >
                <NativeSelectOption v-for="kind in GENERIC_MARKER_KINDS" :key="kind" :value="kind">
                  {{ t(markerKindLabelKey(kind)) }}
                </NativeSelectOption>
              </NativeSelect>
            </div>
            <div class="space-y-1.5">
              <Label for="map-editor-marker-label">{{ t('mapEditor.marker.label') }}</Label>
              <Input
                id="map-editor-marker-label"
                v-model="labelDraft"
                maxlength="120"
                :placeholder="t('mapEditor.marker.labelPlaceholder')"
                data-testid="marker-label"
                @change="saveLabel"
                @keydown.enter.prevent="saveLabel"
              />
            </div>
          </template>
          <p v-else class="text-muted-foreground text-sm">
            {{ t('mapEditor.marker.locationHint') }}
          </p>

          <p id="map-editor-nudge-hint" class="text-muted-foreground text-xs">
            {{ t('mapEditor.marker.nudgeHint') }}
          </p>

          <Button
            size="sm"
            variant="outline"
            class="text-destructive w-full"
            data-testid="marker-delete"
            @click="deleteMarker(selectedMarker)"
          >
            <Trash2 />
            {{ t('mapEditor.marker.delete') }}
          </Button>
        </section>

        <div
          class="rounded-lg border p-3 max-lg:border-0 max-lg:p-0"
          :class="hasSelection ? 'max-lg:hidden' : ''"
        >
          <VenueMarkerPalette
            :locations="locations"
            :placed-location-ids="placedLocationIds"
            :active="placing?.key ?? null"
            :disabled="creatingMarker"
            @pick-location="pickLocation"
            @pick-kind="pickKind"
          />
        </div>

        <section
          class="space-y-2 rounded-lg border p-3 max-lg:rounded-none max-lg:border-0 max-lg:border-t max-lg:px-0 max-lg:pb-0"
          :class="[
            wantsPicture.has(plan.id) && !hasImage ? 'ring-primary/40 ring-2' : '',
            hasSelection ? 'max-lg:hidden' : '',
          ]"
          :aria-label="t('mapEditor.picture.title')"
          data-testid="picture-card"
        >
          <p class="text-sm font-medium">{{ t('mapEditor.picture.title') }}</p>
          <p
            v-if="sandbox"
            class="text-muted-foreground text-sm"
            role="note"
            data-testid="plan-upload-sandbox"
          >
            {{
              hasImage ? t('mapEditor.upload.sandboxReplace') : t('mapEditor.create.pictureSandbox')
            }}
          </p>
          <template v-else-if="!hasImage">
            <div v-if="wantsPicture.has(plan.id)" class="h-56">
              <VenuePlanUpload :key="`zone-${plan.id}`" :plan-id="plan.id" @uploaded="onUploaded" />
            </div>
            <VenuePlanUpload
              v-else
              :key="`add-${plan.id}`"
              :plan-id="plan.id"
              compact
              :label="t('mapEditor.picture.add')"
              :hint="
                history.shapes.value.length > 0
                  ? t('mapEditor.draw.stretchHint')
                  : t('mapEditor.upload.hint')
              "
              @uploaded="onUploaded"
            />
          </template>
          <template v-else>
            <VenuePlanUpload :plan-id="plan.id" compact @uploaded="onUploaded" />
            <Button
              size="sm"
              variant="outline"
              class="text-destructive"
              data-testid="picture-remove"
              @click="removePicture"
            >
              <ImageMinus />
              {{ t('mapEditor.picture.remove') }}
            </Button>
            <p
              v-if="history.shapes.value.length > 0"
              class="text-muted-foreground text-xs"
              data-testid="picture-stretch-hint"
            >
              {{ t('mapEditor.draw.stretchHint') }}
            </p>
          </template>
        </section>
      </aside>
    </div>

    <VenuePlanCreateDialog
      ref="createDialog"
      v-model:open="createOpen"
      :sandbox="sandbox"
      :saving="creating"
      @submit="createPlan"
    />

    <VenueTemplateNameDialog
      v-model:open="saveTemplateOpen"
      :title="t('mapEditor.templates.saveTitle')"
      :description="t('mapEditor.templates.saveDescription')"
      :submit-label="t('mapEditor.templates.saveSubmit')"
      :initial-name="plan?.name ?? ''"
      :saving="savingTemplate"
      @submit="submitSaveTemplate"
    />

    <ResponsiveDialog v-model:open="renameDialog.open">
      <ResponsiveDialogContent>
        <ResponsiveDialogHeader>
          <ResponsiveDialogTitle>{{ t('mapEditor.plans.renameTitle') }}</ResponsiveDialogTitle>
          <ResponsiveDialogDescription class="sr-only">
            {{ t('mapEditor.plans.renameDescription') }}
          </ResponsiveDialogDescription>
        </ResponsiveDialogHeader>
        <ResponsiveDialogBody class="pb-2">
          <form id="map-editor-plan-name" class="space-y-1.5" @submit.prevent="submitRename">
            <Label for="map-editor-plan-name-input">{{ t('mapEditor.plans.name') }}</Label>
            <Input
              id="map-editor-plan-name-input"
              v-model="renameDialog.name"
              maxlength="120"
              :placeholder="t('mapEditor.plans.namePlaceholder')"
              data-testid="plan-rename-input"
            />
          </form>
        </ResponsiveDialogBody>
        <ResponsiveDialogFooter>
          <Button variant="outline" @click="renameDialog.open = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button
            type="submit"
            form="map-editor-plan-name"
            :disabled="!trimmedName || savingName"
            data-testid="plan-rename-save"
          >
            {{ t('common.actions.save') }}
          </Button>
        </ResponsiveDialogFooter>
      </ResponsiveDialogContent>
    </ResponsiveDialog>
  </div>
</template>
