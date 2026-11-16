<script setup lang="ts">
/**
 * A list's link as a QR code to print and hang up: on a white tile, so it
 * scans in dark mode too, with a button that saves a large PNG of it.
 */
import { ref } from 'vue'

import { Download } from '@lucide/vue'
import QRCode from 'qrcode'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import QrCode from '@/components/print/QrCode.vue'

import { toastApiError } from '@/lib/api-errors'

const props = defineProps<{
  url: string
  /** Names the saved file. */
  code: string
}>()

const { t } = useI18n()

/** Big enough for a poster; the screen shows the same code smaller. */
const PNG_SIZE = 1024

const saving = ref(false)

async function savePng() {
  saving.value = true
  try {
    const href = await QRCode.toDataURL(props.url, {
      width: PNG_SIZE,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: { dark: '#000000', light: '#ffffff' },
    })
    const link = document.createElement('a')
    link.href = href
    link.download = `qr-${props.code}.png`
    link.click()
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-4" data-testid="shared-list-qr">
    <div class="shrink-0 rounded-lg border bg-white p-2.5">
      <QrCode
        :value="props.url"
        :size="152"
        :pixel-ratio="2"
        :alt="t('sharedLists.detail.qrAlt', { url: props.url })"
      />
    </div>
    <div class="grid max-w-[32ch] gap-2">
      <p class="text-[13px] text-muted-foreground">{{ t('sharedLists.detail.qrHint') }}</p>
      <Button
        variant="outline"
        size="sm"
        class="w-fit max-sm:h-10"
        :disabled="saving"
        data-testid="shared-list-qr-save"
        @click="savePng"
      >
        <Download aria-hidden="true" />
        {{ t('sharedLists.actions.savePng') }}
      </Button>
    </div>
  </div>
</template>
