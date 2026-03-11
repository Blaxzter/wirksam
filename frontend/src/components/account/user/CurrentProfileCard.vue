<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <UserIcon class="h-5 w-5" />
        {{ $t('user.settings.profile.current.title') }}
      </CardTitle>
      <CardDescription>{{ $t('user.settings.profile.current.subtitle') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <div class="flex items-start gap-6">
        <!-- Avatar -->
        <div class="flex flex-col items-center gap-4">
          <Avatar class="h-24 w-24">
            <AvatarImage v-if="user?.picture" :src="user.picture" :alt="displayName" />
            <AvatarFallback class="text-xl">
              {{ initials }}
            </AvatarFallback>
          </Avatar>
        </div>

        <!-- User Info -->
        <div class="flex-1 grid gap-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label class="text-sm font-medium text-muted-foreground">{{
                $t('user.settings.profile.current.fields.name')
              }}</Label>
              <p class="text-sm">
                {{ user?.name || $t('user.settings.profile.current.fields.notProvided') }}
              </p>
            </div>
            <div>
              <div class="flex items-center gap-2">
                <Label class="text-sm font-medium text-muted-foreground">{{
                  $t('user.settings.profile.current.fields.email')
                }}</Label>
                <Badge variant="outline">
                  {{
                    user?.email_verified
                      ? $t('user.settings.profile.current.fields.verified')
                      : $t('user.settings.profile.current.fields.unverified')
                  }}
                </Badge>
              </div>
              <p class="text-sm">
                {{ user?.email || $t('user.settings.profile.current.fields.notProvided') }}
              </p>
            </div>
            <div>
              <Label class="text-sm font-medium text-muted-foreground">{{
                $t('user.settings.profile.current.fields.nickname')
              }}</Label>
              <p class="text-sm">
                {{ user?.nickname || $t('user.settings.profile.current.fields.notProvided') }}
              </p>
            </div>
            <div>
              <Label class="text-sm font-medium text-muted-foreground">{{
                $t('user.settings.profile.current.fields.authProvider')
              }}</Label>
              <Badge
                :variant="authProvider.variant"
                class="text-xs flex items-center gap-2 w-fit mt-1"
              >
                <SimpleIcon :iconData="authProvider.icon" />
                {{ authProvider.name }}
              </Badge>
            </div>
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { UserIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'

import SimpleIcon from '@/components/utils/SimpleIcon.vue'

import type { User } from '@auth0/auth0-vue'

import { useAuthProvider } from './useAuthProvider'

interface Props {
  user: User | undefined
}

const props = defineProps<Props>()
useI18n()

// Computed properties
const displayName = computed(
  () => props.user?.name || props.user?.nickname || props.user?.email || 'User',
)

const initials = computed(() => {
  if (props.user?.name) {
    return props.user.name
      .split(' ')
      .map((n: string) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }
  if (props.user?.email) {
    return props.user.email[0].toUpperCase()
  }
  return 'U'
})

// Determine auth provider from sub field
const authProvider = useAuthProvider(props.user)
</script>
