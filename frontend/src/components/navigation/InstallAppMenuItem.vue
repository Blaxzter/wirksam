<script setup lang="ts">
import { Download } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useDialog } from '@/composables/useDialog'
import { useInstallPrompt } from '@/composables/useInstallPrompt'

import { DropdownMenuItem } from '@/components/ui/dropdown-menu'

/**
 * "Install app" for the user menus. Shown only while installing is possible:
 * a browser prompt is ready (Chromium), or the device is an iPhone/iPad, where
 * Safari installs only by hand and the item says how.
 */
const { t } = useI18n()
const { info } = useDialog()
const { canInstall, canPrompt, install } = useInstallPrompt()

async function onSelect() {
  if (canPrompt.value) {
    await install()
    return
  }
  await info({
    title: t('navigation.user.install.iosTitle'),
    text: t('navigation.user.install.iosSteps'),
    confirmText: t('common.actions.close'),
  })
}
</script>

<template>
  <DropdownMenuItem v-if="canInstall" data-testid="user-menu-install-app" @click="onSelect">
    <Download />
    {{ t('navigation.user.actions.installApp') }}
  </DropdownMenuItem>
</template>
