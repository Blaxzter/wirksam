<script setup lang="ts">
import { ArrowLeftIcon } from '@lucide/vue'
import { useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'

const router = useRouter()

const goBackToHome = () => {
  router.push({ name: 'landing' })
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between">
      <div class="space-y-2">
        <h1 class="text-3xl font-bold">{{ $t('preauth.terms.title') }}</h1>
        <p class="text-muted-foreground">
          {{ $t('preauth.terms.lastUpdated') }}
        </p>
      </div>
      <Button @click="goBackToHome" variant="ghost" size="sm" class="gap-2">
        <ArrowLeftIcon class="h-4 w-4" />
        {{ $t('preauth.terms.backToHome') }}
      </Button>
    </div>

    <div class="space-y-8 max-w-prose">
      <!-- Scope -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.scope.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.scope.description') }}</p>
      </section>

      <!-- Account -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.account.title') }}</h2>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.terms.account.items.registration') }}</li>
          <li>{{ $t('preauth.terms.account.items.accuracy') }}</li>
          <li>{{ $t('preauth.terms.account.items.security') }}</li>
          <li>{{ $t('preauth.terms.account.items.access') }}</li>
        </ul>
      </section>

      <!-- Usage rules -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.usage.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.usage.intro') }}</p>
        <ul class="list-disc pl-6 space-y-1 text-muted-foreground">
          <li>{{ $t('preauth.terms.usage.items.lawful') }}</li>
          <li>{{ $t('preauth.terms.usage.items.respectful') }}</li>
          <li>{{ $t('preauth.terms.usage.items.reliable') }}</li>
          <li>{{ $t('preauth.terms.usage.items.noAbuse') }}</li>
        </ul>
      </section>

      <!-- Bookings -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.bookings.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.bookings.description') }}</p>
      </section>

      <!-- Availability -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.availability.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.availability.description') }}</p>
      </section>

      <!-- Liability -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.liability.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.liability.description') }}</p>
      </section>

      <!-- Termination -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.termination.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.termination.description') }}</p>
      </section>

      <!-- Changes -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.changes.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.changes.description') }}</p>
      </section>

      <!-- Governing law -->
      <section class="space-y-3">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.terms.law.title') }}</h2>
        <p class="text-muted-foreground">{{ $t('preauth.terms.law.description') }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped></style>
