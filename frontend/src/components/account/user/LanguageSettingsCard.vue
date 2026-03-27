<script setup lang="ts">
import { GlobeIcon, InfoIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import LanguageSwitch from '@/components/utils/LanguageSwitch.vue'

useI18n()
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <GlobeIcon class="h-5 w-5" />
        {{ $t('user.settings.language.title') }}
      </CardTitle>
      <CardDescription>
        {{ $t('user.settings.language.description') }}
      </CardDescription>
    </CardHeader>
    <CardContent>
      <div class="flex items-center justify-between">
        <div class="space-y-1">
          <p class="text-sm font-medium">{{ $t('user.settings.language.current') }}</p>
          <p class="text-sm text-muted-foreground">
            {{ $t('user.settings.language.currentDescription') }}
          </p>
        </div>
        <LanguageSwitch variant="outline" size="default" :show-text="true" />
      </div>
      <p class="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
        <InfoIcon class="h-3.5 w-3.5 shrink-0" />
        {{ $t('user.settings.language.notificationHint') }}
      </p>
    </CardContent>
  </Card>
</template>
