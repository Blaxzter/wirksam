<script setup lang="ts">
/**
 * The wizard's last step, once the list is open: its link to copy, a text for
 * the group that can be edited before copying, and a QR code for a notice,
 * which "Aushang drucken" prints with the list's shifts.
 */
import { Check, Copy, Printer } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useClipboardCopy } from '@/composables/useClipboardCopy'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

import QrCode from '@/components/print/QrCode.vue'

const props = defineProps<{ url: string }>()

const emit = defineEmits<{ print: [] }>()

const message = defineModel<string>('message', { required: true })

const { t } = useI18n()
const { copied, copy } = useClipboardCopy<'link' | 'text'>()

async function copyLink() {
  if (await copy('link', props.url)) {
    toast.success(t('sharedListWizard.share.linkCopied'))
  } else {
    // A blocked clipboard: the link itself can still be copied by hand.
    toast.info(props.url)
  }
}

async function copyText() {
  if (await copy('text', message.value)) toast.success(t('sharedListWizard.share.textCopied'))
  else toast.warning(t('sharedListWizard.share.copyFailed'))
}

function selectAll(event: FocusEvent) {
  ;(event.target as HTMLInputElement).select()
}
</script>

<template>
  <div class="grid gap-6">
    <div
      class="flex items-center gap-3 rounded-lg bg-primary/10 p-3"
      data-testid="wizard-share-success"
    >
      <span
        class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"
        aria-hidden="true"
      >
        <Check class="size-5" />
      </span>
      <div class="grid">
        <p class="font-semibold">{{ t('sharedListWizard.share.success.title') }}</p>
        <p class="text-sm">{{ t('sharedListWizard.share.success.text') }}</p>
      </div>
    </div>

    <div class="grid gap-2">
      <Label for="wizard-share-link">{{ t('sharedListWizard.share.linkLabel') }}</Label>
      <div class="flex flex-col gap-2 sm:flex-row">
        <Input
          id="wizard-share-link"
          :model-value="url"
          readonly
          class="font-mono"
          data-testid="wizard-share-link"
          @focus="selectAll"
        />
        <Button type="button" class="shrink-0" data-testid="wizard-copy-link" @click="copyLink">
          <Check v-if="copied === 'link'" aria-hidden="true" />
          <Copy v-else aria-hidden="true" />
          {{
            copied === 'link'
              ? t('sharedListWizard.share.copied')
              : t('sharedListWizard.share.copyLink')
          }}
        </Button>
      </div>
    </div>

    <div class="grid gap-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
      <div class="grid gap-2">
        <Label for="wizard-share-message">{{ t('sharedListWizard.share.message.label') }}</Label>
        <Textarea
          id="wizard-share-message"
          v-model="message"
          rows="12"
          class="min-h-64 text-sm"
          aria-describedby="wizard-share-message-hint"
          data-testid="wizard-share-message"
        />
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Button
            type="button"
            variant="outline"
            class="shrink-0"
            data-testid="wizard-copy-text"
            @click="copyText"
          >
            <Check v-if="copied === 'text'" aria-hidden="true" />
            <Copy v-else aria-hidden="true" />
            {{
              copied === 'text'
                ? t('sharedListWizard.share.copied')
                : t('sharedListWizard.share.copyText')
            }}
          </Button>
          <p id="wizard-share-message-hint" class="text-xs text-muted-foreground">
            {{ t('sharedListWizard.share.message.hint') }}
          </p>
        </div>
      </div>
      <figure class="grid justify-items-center gap-2 text-center">
        <!-- White in either theme: a camera reads dark on light. -->
        <div class="rounded-lg bg-white p-3">
          <QrCode
            :value="url"
            :size="160"
            :pixel-ratio="2"
            :alt="t('sharedListWizard.share.qr.alt')"
            data-testid="wizard-share-qr"
          />
        </div>
        <figcaption class="text-xs text-muted-foreground">
          {{ t('sharedListWizard.share.qr.hint') }}
        </figcaption>
        <Button
          type="button"
          variant="outline"
          size="sm"
          class="max-sm:h-10"
          data-testid="wizard-print-notice"
          @click="emit('print')"
        >
          <Printer aria-hidden="true" />
          {{ t('print.printNotice') }}
        </Button>
      </figure>
    </div>
  </div>
</template>
