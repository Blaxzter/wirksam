<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const router = useRouter()
const { locale } = useI18n()

const stepDefs = [
  {
    key: 'details',
    icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
    file: 'create-step1-details',
  },
  {
    key: 'dates',
    icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',
    file: 'create-step2-dates',
  },
  {
    key: 'schedule',
    icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
    file: 'create-step3-schedule',
  },
  {
    key: 'remainder',
    icon: 'M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm0 8a1 1 0 011-1h6a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1v-2z',
  },
  {
    key: 'preview',
    icon: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z',
    file: 'create-step5-preview',
  },
  { key: 'publish', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
]

const steps = computed(() =>
  stepDefs.map((s) => ({
    key: s.key,
    icon: s.icon,
    image: s.file ? `/screenshots/${locale.value}/${s.file}.png` : undefined,
  })),
)

const features = ['batchSlots', 'smartRegeneration', 'dryRun', 'overrides']

const featureIcons: Record<string, string> = {
  batchSlots:
    'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
  smartRegeneration:
    'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  dryRun:
    'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4',
  overrides:
    'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
}

const flowSteps = [
  'Event Dates',
  'Schedule Config',
  'Per-Day Overrides',
  'Generate Slots',
  'Exclude Slots',
  'Save & Publish',
]
</script>

<template>
  <div class="space-y-12 sm:space-y-16 max-w-4xl mx-auto">
    <!-- Header -->
    <div class="space-y-4">
      <Button data-testid="btn-back" variant="ghost" size="sm" @click="router.push({ name: 'landing' })">
        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M15 19l-7-7 7-7"
          />
        </svg>
        {{ $t('preauth.howItWorks.backToHome') }}
      </Button>

      <div class="text-center space-y-3">
        <Badge variant="secondary" class="text-sm px-3 py-1">How It Works</Badge>
        <h1 data-testid="page-heading" class="text-2xl sm:text-4xl font-bold tracking-tight">
          {{ $t('preauth.howItWorks.title') }}
        </h1>
        <p class="text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
          {{ $t('preauth.howItWorks.subtitle') }}
        </p>
      </div>
    </div>

    <!-- Steps (Desktop: timeline left, content right) -->
    <div class="hidden sm:block space-y-6">
      <div v-for="(step, index) in steps" :key="step.key" class="flex gap-6 items-start">
        <div class="flex flex-col items-center shrink-0">
          <div
            class="w-12 h-12 rounded-full bg-primary text-primary-foreground flex items-center justify-center"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                :d="step.icon"
              />
            </svg>
          </div>
          <div v-if="index < steps.length - 1" class="w-px flex-1 bg-border mt-2" />
        </div>
        <div class="pt-2 pb-4 min-w-0 flex-1">
          <h3 class="text-xl font-semibold mb-1">
            {{ $t(`preauth.howItWorks.steps.${step.key}.title`) }}
          </h3>
          <p class="text-muted-foreground leading-relaxed">
            {{ $t(`preauth.howItWorks.steps.${step.key}.description`) }}
          </p>
          <div v-if="step.image" class="mt-4 rounded-lg border overflow-hidden bg-muted/20">
            <img
              :src="step.image"
              :alt="$t(`preauth.howItWorks.steps.${step.key}.title`)"
              class="w-full h-auto"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Steps (Mobile: icon above content, stacked) -->
    <div class="sm:hidden space-y-8">
      <div v-for="step in steps" :key="step.key" class="flex flex-col items-center text-center">
        <div
          class="w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center mb-3"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="step.icon" />
          </svg>
        </div>
        <h3 class="text-lg font-semibold mb-1">
          {{ $t(`preauth.howItWorks.steps.${step.key}.title`) }}
        </h3>
        <p class="text-sm text-muted-foreground leading-relaxed">
          {{ $t(`preauth.howItWorks.steps.${step.key}.description`) }}
        </p>
        <div v-if="step.image" class="mt-3 rounded-lg border overflow-hidden bg-muted/20 w-full">
          <img
            :src="step.image"
            :alt="$t(`preauth.howItWorks.steps.${step.key}.title`)"
            class="w-full h-auto"
          />
        </div>
      </div>
    </div>

    <!-- Visual flow diagram -->
    <div class="border rounded-xl p-4 sm:p-8 bg-muted/30">
      <h2
        class="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4 sm:mb-6 text-center"
      >
        Slot Generation Flow
      </h2>
      <!-- Desktop: horizontal flow -->
      <div class="hidden sm:flex flex-wrap items-center justify-center gap-3 text-sm">
        <template v-for="(step, i) in flowSteps" :key="step">
          <div
            class="px-4 py-2 rounded-lg border font-medium"
            :class="
              step === 'Generate Slots' ? 'bg-primary text-primary-foreground' : 'bg-background'
            "
          >
            {{ step }}
          </div>
          <svg
            v-if="i < flowSteps.length - 1"
            class="w-5 h-5 text-muted-foreground shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 5l7 7-7 7"
            />
          </svg>
        </template>
      </div>
      <!-- Mobile: vertical flow -->
      <div class="flex sm:hidden flex-col items-center gap-2 text-sm">
        <template v-for="(step, i) in flowSteps" :key="step">
          <div
            class="px-4 py-2 rounded-lg border font-medium w-full text-center"
            :class="
              step === 'Generate Slots' ? 'bg-primary text-primary-foreground' : 'bg-background'
            "
          >
            {{ step }}
          </div>
          <svg
            v-if="i < flowSteps.length - 1"
            class="w-5 h-5 text-muted-foreground shrink-0 rotate-90"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 5l7 7-7 7"
            />
          </svg>
        </template>
      </div>
    </div>

    <!-- Advanced Features -->
    <div class="space-y-6 sm:space-y-8">
      <div class="text-center">
        <h2 class="text-xl sm:text-2xl font-bold">{{ $t('preauth.howItWorks.features.title') }}</h2>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        <div
          v-for="feature in features"
          :key="feature"
          class="p-4 sm:p-6 border rounded-lg space-y-2 sm:space-y-3"
        >
          <div class="flex items-center gap-3">
            <div
              class="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0"
            >
              <svg
                class="w-4 h-4 sm:w-5 sm:h-5 text-primary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  :d="featureIcons[feature]"
                />
              </svg>
            </div>
            <h3 class="font-semibold text-sm sm:text-base">
              {{ $t(`preauth.howItWorks.features.${feature}.title`) }}
            </h3>
          </div>
          <p class="text-muted-foreground text-xs sm:text-sm leading-relaxed">
            {{ $t(`preauth.howItWorks.features.${feature}.description`) }}
          </p>
        </div>
      </div>
    </div>

    <!-- CTA -->
    <div class="text-center space-y-4 pb-8">
      <p class="text-muted-foreground">Ready to get started?</p>
      <Button size="lg" @click="router.push({ name: 'landing' })">
        {{ $t('preauth.howItWorks.backToHome') }}
      </Button>
    </div>
  </div>
</template>

<style scoped></style>
