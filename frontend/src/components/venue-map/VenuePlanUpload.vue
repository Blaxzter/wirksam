<script setup lang="ts">
import { ref } from 'vue'

import { ImageUp, LoaderIcon, UploadIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Button } from '@/components/ui/button'

import type { VenuePlanRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * Picks a picture for a venue plan and uploads it as-is — no cropper, a floor
 * plan should keep its full extent; the server rotates, shrinks and re-encodes.
 *
 * Two looks: the default is a drop zone that fills its parent (a plan without
 * a picture yet), `compact` is a single "Replace picture" button. Either way
 * the markers keep their place, because they are stored relative to the image.
 */
const props = withDefaults(
  defineProps<{
    planId: string
    compact?: boolean
  }>(),
  { compact: false },
)

const emit = defineEmits<{
  uploaded: [plan: VenuePlanRead]
}>()

const { t } = useI18n()
const { getAuthToken } = useAuthenticatedClient()

const ACCEPT = 'image/png,image/jpeg,image/webp,image/gif'
const ACCEPTED_TYPES = new Set(ACCEPT.split(','))

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const dragOver = ref(false)
// dragenter/dragleave fire for every child; count them so the highlight does
// not flicker while the pointer crosses the hint text.
let dragDepth = 0

// The server reads only the first frame of a GIF anyway, but flattening it
// here keeps the upload small. createImageBitmap is spec'd to return only the
// first frame. (Same as AvatarPicker.)
async function flattenAnimated(file: File): Promise<File> {
  if (file.type !== 'image/gif') return file
  const bitmap = await createImageBitmap(file)
  try {
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(bitmap, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!blob) return file
    return new File([blob], file.name.replace(/\.gif$/i, '.png'), { type: 'image/png' })
  } finally {
    bitmap.close()
  }
}

/**
 * Raw `fetch` (the generated client does not do multipart) answers with a
 * plain Response; shape a failure like an axios error so `toastApiError`
 * translates the problem `code` (`venue_plan.invalid_image`,
 * `sandbox.upload_disabled`, …) the same way as for every other request.
 */
async function responseError(response: Response) {
  const data: unknown = await response.json().catch(() => null)
  return Object.assign(new Error(`Upload failed: ${response.status}`), {
    isAxiosError: true,
    response: { status: response.status, data },
  })
}

async function upload(file: File) {
  if (uploading.value) return
  if (!ACCEPTED_TYPES.has(file.type)) {
    toast.error(t('errorCodes.venue_plan.invalid_image'))
    return
  }
  uploading.value = true
  try {
    let body: File = file
    try {
      body = await flattenAnimated(file)
    } catch {
      // Let the server decide what it can read.
    }
    const formData = new FormData()
    formData.append('file', body, body.name)
    const token = await getAuthToken()
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/venue-plans/${props.planId}/image`,
      { method: 'PUT', headers: { Authorization: `Bearer ${token}` }, body: formData },
    )
    if (!response.ok) throw await responseError(response)
    const plan = (await response.json()) as VenuePlanRead
    toast.success(t('mapEditor.upload.success'))
    emit('uploaded', plan)
  } catch (error) {
    toastApiError(error)
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function onFileSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void upload(file)
}

function onDragEnter() {
  dragDepth++
  dragOver.value = true
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragOver.value = false
}

function onDrop(event: DragEvent) {
  dragDepth = 0
  dragOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void upload(file)
}

function pick() {
  fileInput.value?.click()
}

defineExpose({ pick })
</script>

<template>
  <input
    ref="fileInput"
    type="file"
    :accept="ACCEPT"
    class="hidden"
    data-testid="plan-upload-input"
    @change="onFileSelected"
  />

  <div v-if="compact" class="space-y-1">
    <Button
      type="button"
      variant="outline"
      size="sm"
      :disabled="uploading"
      data-testid="plan-upload-replace"
      @click="pick"
    >
      <LoaderIcon v-if="uploading" class="animate-spin" />
      <UploadIcon v-else />
      {{ uploading ? t('mapEditor.upload.uploading') : t('mapEditor.upload.replace') }}
    </Button>
    <p class="text-muted-foreground text-xs">{{ t('mapEditor.upload.replaceHint') }}</p>
  </div>

  <div
    v-else
    class="flex h-full w-full flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-6 text-center transition-colors"
    :class="dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/30'"
    data-testid="plan-upload-zone"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <ImageUp class="text-muted-foreground size-10" aria-hidden="true" />
    <div class="space-y-1">
      <p class="font-medium">
        {{ dragOver ? t('mapEditor.upload.dropHere') : t('mapEditor.upload.title') }}
      </p>
      <p class="text-muted-foreground text-sm">{{ t('mapEditor.upload.hint') }}</p>
    </div>
    <Button type="button" :disabled="uploading" data-testid="plan-upload-button" @click="pick">
      <LoaderIcon v-if="uploading" class="animate-spin" />
      <UploadIcon v-else />
      {{ uploading ? t('mapEditor.upload.uploading') : t('mapEditor.upload.choose') }}
    </Button>
  </div>
</template>
