<script setup lang="ts">
import { FlaskConicalIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

/**
 * On a demo's list, and on the page of whoever signed up through one: this is
 * a demo. Nothing is mailed, and every sign-up goes with the demo. Whatever a
 * visitor wrote into the list's heading, the page cannot pass for a real one.
 */
const { t } = useI18n()
</script>

<template>
  <div
    role="note"
    class="flex items-start gap-2.5 rounded-xl border border-dashed border-primary/50 bg-primary/5 p-3 text-sm"
    data-testid="guest-demo-notice"
  >
    <FlaskConicalIcon class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
    <p>
      <span class="font-semibold">{{ t('guestSignup.demo.title') }}</span>
      {{ t('guestSignup.demo.text') }}
    </p>
  </div>
</template>
