<script setup lang="ts">
import { Bell, ChevronRight } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const { t } = useI18n()
const router = useRouter()

function goToPreferences() {
  router.push({ name: 'notification-preferences' })
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <Bell class="h-5 w-5" />
        {{ t('notifications.settings.title') }}
      </CardTitle>
      <CardDescription>
        {{ t('notifications.settings.description') }}
      </CardDescription>
    </CardHeader>
    <CardContent>
      <Button variant="outline" class="w-full justify-between" @click="goToPreferences">
        {{ t('notifications.settings.manage') }}
        <ChevronRight class="h-4 w-4" />
      </Button>
    </CardContent>
  </Card>
</template>
