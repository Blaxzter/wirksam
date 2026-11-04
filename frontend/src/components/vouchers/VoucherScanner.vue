<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { Loader2 } from '@lucide/vue'
import type QrScanner from 'qr-scanner'
import { useI18n } from 'vue-i18n'

import { type CameraProblem, classifyCameraError } from '@/lib/vouchers'

/**
 * The camera view that reads volunteers' QR codes. The only file that loads
 * `qr-scanner`, and only once it is on screen, so neither the library nor its
 * decoder worker reaches any page that does not scan.
 *
 * The scanner reports every frame it decodes, many times a second, so the
 * parent decides what to act on. `paused` only stops this component from
 * passing detections on; the camera keeps running, because stopping it
 * between two people would ask iOS for permission again.
 *
 * Never mount it inside an element hidden with `v-show` or `hidden`: the
 * library forces a hidden video visible.
 */
const props = defineProps<{ paused?: boolean }>()

export type ScannerError = 'insecure' | CameraProblem

const emit = defineEmits<{
  /** The raw text of a QR code in view. */
  detect: [data: string]
  error: [kind: ScannerError]
}>()

const { t } = useI18n()

/**
 * How long a camera that has handed over its stream may take to show a first
 * picture. Counted from the stream, not from the start, so a permission prompt
 * the redeemer is still reading never runs into it.
 */
const NO_PICTURE_MS = 8000

const video = ref<HTMLVideoElement | null>(null)
const starting = ref(true)
const failed = ref(false)

let scanner: QrScanner | null = null
let unmounted = false
let watchdog: ReturnType<typeof setInterval> | null = null

function stopWatchdog() {
  if (watchdog) clearInterval(watchdog)
  watchdog = null
}

function fail(kind: ScannerError) {
  if (failed.value) return
  stopWatchdog()
  scanner?.destroy()
  scanner = null
  failed.value = true
  starting.value = false
  emit('error', kind)
}

/** The camera permission's state, where the browser can tell. */
async function cameraPermission(): Promise<PermissionState | null> {
  try {
    const status = await navigator.permissions?.query({ name: 'camera' as PermissionName })
    return status?.state ?? null
  } catch {
    // Firefox does not know the name; nothing to go on, then.
    return null
  }
}

/**
 * Some cameras hand over a stream that never delivers a frame (a webcam held
 * by another app, a broken driver), and the library then waits for ever.
 */
function watchForPicture() {
  let streamSince: number | null = null
  watchdog = setInterval(() => {
    const el = video.value
    if (!el || !starting.value) return stopWatchdog()
    if (!el.srcObject) return
    streamSince ??= Date.now()
    if (el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return
    if (Date.now() - streamSince >= NO_PICTURE_MS) fail('other')
  }, 500)
}

onMounted(async () => {
  if (!window.isSecureContext) return fail('insecure')
  if (!navigator.mediaDevices?.getUserMedia) return fail('no-camera')
  try {
    const { default: QrScannerClass } = await import('qr-scanner')
    if (unmounted || !video.value) return
    scanner = new QrScannerClass(
      video.value,
      (result) => {
        if (!props.paused) emit('detect', result.data)
      },
      {
        preferredCamera: 'environment',
        maxScansPerSecond: 8,
        highlightScanRegion: true,
        highlightCodeOutline: true,
        onDecodeError: () => {},
      },
    )
    watchForPicture()
    await scanner.start()
    if (failed.value) return
    stopWatchdog()
    starting.value = false
  } catch (err) {
    if (unmounted || failed.value) return
    const permission = await cameraPermission()
    if (unmounted) return
    fail(classifyCameraError(err, permission))
  }
})

onBeforeUnmount(() => {
  unmounted = true
  stopWatchdog()
  scanner?.destroy()
  scanner = null
})
</script>

<template>
  <!-- `relative`: the library places its highlight overlay next to the video. -->
  <div
    class="relative aspect-square w-full overflow-hidden rounded-lg bg-black"
    data-testid="voucher-scanner"
  >
    <video
      ref="video"
      class="h-full w-full object-cover"
      muted
      playsinline
      :aria-label="t('vouchers.redeem.scanHint')"
    />
    <div
      v-if="starting && !failed"
      class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-white/80"
    >
      <Loader2 class="size-6 animate-spin" aria-hidden="true" />
      {{ t('vouchers.redeem.cameraStarting') }}
    </div>
  </div>
</template>
