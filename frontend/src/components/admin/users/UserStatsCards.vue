<script setup lang="ts">
import { computed } from 'vue'

import { UserCheck, UserLock, UserRoundX, UserX, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const props = defineProps<{
  total: number
  active: number
  pending: number
  rejected: number
  suspended: number
  /** Show the approval-queue cards (pending, rejected). */
  showQueue: boolean
}>()

const columns = computed(() => (props.showQueue ? 'lg:grid-cols-5' : 'lg:grid-cols-3'))

const { t } = useI18n()
</script>

<template>
  <div data-testid="section-stats" class="grid gap-4 sm:grid-cols-2" :class="columns">
    <Card data-testid="stat-total">
      <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle class="text-sm font-medium">{{ t('admin.users.statsTotal') }}</CardTitle>
        <Users class="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ total }}</div>
      </CardContent>
    </Card>
    <Card data-testid="stat-active">
      <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle class="text-sm font-medium">{{ t('admin.users.active') }}</CardTitle>
        <UserCheck class="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ active }}</div>
      </CardContent>
    </Card>
    <Card v-if="showQueue" data-testid="stat-pending">
      <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle class="text-sm font-medium">{{ t('admin.users.pending') }}</CardTitle>
        <UserX class="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ pending }}</div>
      </CardContent>
    </Card>
    <Card v-if="showQueue" data-testid="stat-rejected">
      <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle class="text-sm font-medium">{{ t('admin.users.rejected') }}</CardTitle>
        <UserRoundX class="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ rejected }}</div>
      </CardContent>
    </Card>
    <Card data-testid="stat-suspended">
      <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle class="text-sm font-medium">{{ t('admin.users.suspended') }}</CardTitle>
        <UserLock class="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div class="text-2xl font-bold">{{ suspended }}</div>
      </CardContent>
    </Card>
  </div>
</template>
