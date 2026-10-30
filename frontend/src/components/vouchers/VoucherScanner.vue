<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { Loader2 } from '@lucide/vue'
import type QrScanner from 'qr-scanner'
import { useI18n } from 'vue-i18n'

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

export type ScannerError = 'insecure' | 'denied' | 'no-camera' | 'other'

const emit = defineEmits<{
  /** The raw text of a QR code in view. */
  detect: [data: string]
  error: [kind: ScannerError]
}>()

const { t } = useI18n()

const video = ref<HTMLVideoElement | null>(null)
const starting = ref(true)
const failed = ref(false)

let scanner: QrScanner | null = null
let unmounted = false

function classify(err: unknown): ScannerError {
  if (err === 'Camera not found.') return 'no-camera'
  const name = err instanceof Error || err instanceof DOMException ? err.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError')
    return 'denied'
  if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'DevicesNotFoundError')
    return 'no-camera'
  return 'other'
}

function fail(kind: ScannerError) {
  failed.value = true
  starting.value = false
  emit('error', kind)
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
    await scanner.start()
    starting.value = false
  } catch (err) {
    if (unmounted) return
    scanner?.destroy()
    scanner = null
    fail(classify(err))
  }
})

onBeforeUnmount(() => {
  unmounted = true
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
