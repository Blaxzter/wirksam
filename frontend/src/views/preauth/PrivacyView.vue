<script setup lang="ts">
import { computed } from 'vue'

import { ArrowLeftIcon } from '@lucide/vue'
import { useRouter } from 'vue-router'

import { guestRetentionDays, useAppConfig } from '@/composables/useAppConfig'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const router = useRouter()
const config = useAppConfig()

const goBackToHome = () => {
  router.push({ name: 'landing' })
}

/**
 * How many days a list guest's details are kept. The guest pages have it from
 * the API with their list; this page belongs to no list, so it says what the
 * deployment's runtime config says, which carries the backend's number.
 */
const guestRetention = computed(() => guestRetentionDays(config))

const controllerBlock = computed(() => {
  const lines = [config.LEGAL_NAME, config.LEGAL_ADDRESS, config.LEGAL_CITY, 'Germany'].filter(
    Boolean,
  )
  if (config.LEGAL_EMAIL) lines.push('', `Email: ${config.LEGAL_EMAIL}`)
  return lines.join('\n')
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between">
      <div class="space-y-2">
        <h1 class="text-3xl font-bold">{{ $t('preauth.privacy.title') }}</h1>
        <p class="text-muted-foreground">
          {{ $t('preauth.privacy.lastUpdated') }}
        </p>
      </div>
      <Button @click="goBackToHome" variant="ghost" size="sm" class="gap-2">
        <ArrowLeftIcon class="h-4 w-4" />
        {{ $t('preauth.privacy.backToHome') }}
      </Button>
    </div>

    <div class="space-y-8 max-w-prose">
      <!-- Introduction -->
      <section class="space-y-3">
        <p class="text-muted-foreground">
          {{ $t('preauth.privacy.intro') }}
        </p>
      </section>

      <!-- Controller -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.controller.title') }}</h2>
        <Card>
          <CardContent class="text-muted-foreground whitespace-pre-line">
            {{ controllerBlock }}
          </CardContent>
        </Card>
      </section>

      <!-- Data we collect -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.dataCollected.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.dataCollected.intro') }}</p>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.privacy.dataCollected.items.name') }}</li>
          <li>{{ $t('preauth.privacy.dataCollected.items.email') }}</li>
          <li>{{ $t('preauth.privacy.dataCollected.items.credentials') }}</li>
          <li>{{ $t('preauth.privacy.dataCollected.items.picture') }}</li>
          <li>{{ $t('preauth.privacy.dataCollected.items.bookings') }}</li>
        </ul>
      </section>

      <!-- Purpose -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.purpose.title') }}</h2>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.privacy.purpose.items.account') }}</li>
          <li>{{ $t('preauth.privacy.purpose.items.scheduling') }}</li>
          <li>{{ $t('preauth.privacy.purpose.items.notifications') }}</li>
          <li>{{ $t('preauth.privacy.purpose.items.security') }}</li>
        </ul>
      </section>

      <!-- Legal basis -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.legalBasis.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.legalBasis.description') }}</p>
      </section>

      <!-- Signing up through a shared list, without an account -->
      <section class="space-y-3" data-testid="privacy-guests">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.guests.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.intro') }}</p>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.data.intro') }}</p>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.privacy.guests.data.items.name') }}</li>
          <li>{{ $t('preauth.privacy.guests.data.items.email') }}</li>
          <li>{{ $t('preauth.privacy.guests.data.items.phone') }}</li>
          <li>{{ $t('preauth.privacy.guests.data.items.shifts') }}</li>
          <li>{{ $t('preauth.privacy.guests.data.items.vouchers') }}</li>
        </ul>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.purposes.intro') }}</p>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.privacy.guests.purposes.items.signup') }}</li>
          <li>{{ $t('preauth.privacy.guests.purposes.items.confirmation') }}</li>
          <li>{{ $t('preauth.privacy.guests.purposes.items.reminder') }}</li>
          <li>{{ $t('preauth.privacy.guests.purposes.items.contact') }}</li>
        </ul>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.responsible') }}</p>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.legalBasis') }}</p>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.visibility') }}</p>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.vouchers') }}</p>
        <p class="text-muted-foreground" data-testid="privacy-guests-retention">
          {{ $t('preauth.privacy.guests.retention', { days: guestRetention }, guestRetention) }}
        </p>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.erasure') }}</p>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.guests.device') }}</p>
      </section>

      <!-- Third-party services -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.thirdParty.title') }}</h2>
        <div class="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{{ $t('preauth.privacy.thirdParty.email.title') }}</CardTitle>
            </CardHeader>
            <CardContent>
              <p class="text-sm text-muted-foreground">
                {{ $t('preauth.privacy.thirdParty.email.description') }}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{{ $t('preauth.privacy.thirdParty.turnstile.title') }}</CardTitle>
            </CardHeader>
            <CardContent>
              <p class="text-sm text-muted-foreground">
                {{ $t('preauth.privacy.thirdParty.turnstile.description') }}
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      <!-- Data retention -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.retention.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.retention.description') }}</p>
      </section>

      <!-- Your rights -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.rights.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.rights.intro') }}</p>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.privacy.rights.items.access') }}</li>
          <li>{{ $t('preauth.privacy.rights.items.rectification') }}</li>
          <li>{{ $t('preauth.privacy.rights.items.erasure') }}</li>
          <li>{{ $t('preauth.privacy.rights.items.restriction') }}</li>
          <li>{{ $t('preauth.privacy.rights.items.portability') }}</li>
          <li>{{ $t('preauth.privacy.rights.items.objection') }}</li>
        </ul>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.rights.contact') }}</p>
      </section>

      <!-- Cookies -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.cookies.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.cookies.description') }}</p>
      </section>

      <!-- Changes -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.privacy.changes.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.privacy.changes.description') }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped></style>
