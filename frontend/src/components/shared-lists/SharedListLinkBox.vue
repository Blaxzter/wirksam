<script setup lang="ts">
/**
 * The link of an open list in its details: the address itself, copy, the QR
 * code to hang up (shown on request), a notice with it to print, and the
 * preview of the page it opens.
 */
import { computed, ref, useId } from 'vue'

import { Check, Copy, Eye, Printer, QrCode } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import SharedListQrCode from '@/components/shared-lists/SharedListQrCode.vue'

import type { SharedListDetail } from '@/client/types.gen'
import { sharedListUrl } from '@/lib/shared-lists'

const props = defineProps<{
  list: Pick<SharedListDetail, 'id' | 'code'>
  /** Its link was just copied. */
  copied?: boolean
}>()

const emit = defineEmits<{
  copy: []
  preview: []
  print: []
}>()

const { t } = useI18n()
const qrId = useId()

const url = computed(() => sharedListUrl(props.list.code))
const showQr = ref(false)
</script>

<template>
  <div class="grid gap-3" data-testid="shared-list-link">
    <div class="grid gap-2 rounded-xl border bg-muted/40 p-2.5 pl-3">
      <code
        class="min-w-0 font-mono text-[13px] break-all select-all"
        data-testid="shared-list-url"
      >
        {{ url }}
      </code>
      <div class="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          class="max-sm:h-10"
          data-testid="shared-list-link-copy"
          @click="emit('copy')"
        >
          <Check v-if="props.copied" class="text-primary" aria-hidden="true" />
          <Copy v-else aria-hidden="true" />
          {{ t('sharedLists.actions.copy') }}
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="max-sm:h-10"
          :aria-expanded="showQr"
          :aria-controls="qrId"
          data-testid="shared-list-qr-toggle"
          @click="showQr = !showQr"
        >
          <QrCode aria-hidden="true" />
          {{ t('sharedLists.actions.qr') }}
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="max-sm:h-10"
          data-testid="shared-list-link-print"
          @click="emit('print')"
        >
          <Printer aria-hidden="true" />
          {{ t('print.printNotice') }}
        </Button>
        <Button
          variant="outline"
          size="sm"
          class="max-sm:h-10"
          data-testid="shared-list-link-preview"
          @click="emit('preview')"
        >
          <Eye aria-hidden="true" />
          {{ t('sharedLists.actions.preview') }}
        </Button>
      </div>
    </div>
    <div :id="qrId">
      <SharedListQrCode v-if="showQr" :url="url" :code="props.list.code" />
    </div>
  </div>
</template>
