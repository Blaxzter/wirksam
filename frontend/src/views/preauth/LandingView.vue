<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import logo from '@/assets/logo/logo.svg'

import { useAuthStore } from '@/stores/auth'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from '@/components/ui/carousel'
import type { CarouselApi } from '@/components/ui/carousel'

import ChipNav from '@/components/utils/ChipNav.vue'

const authStore = useAuthStore()
const router = useRouter()
const { locale, t } = useI18n()

const slideKeys = [
  { key: 'dashboard', file: 'dashboard' },
  { key: 'eventGroups', file: 'event-groups' },
  { key: 'events', file: 'events' },
  { key: 'eventDetail', file: 'event-detail' },
  { key: 'bookings', file: 'my-bookings' },
  { key: 'notifications', file: 'notification-bell' },
  { key: 'notificationPreferences', file: 'notification-preferences' },
  { key: 'userManagement', file: 'user-management' },
]

const slides = computed(() =>
  slideKeys.map((s) => ({
    key: s.key,
    image: `/screenshots/${locale.value}/${s.file}.png`,
  })),
)

const currentSlide = ref(0)
const carouselApi = ref<CarouselApi>()

function onApiSet(api: CarouselApi) {
  carouselApi.value = api
  if (!api) return

  const syncSlide = () => {
    currentSlide.value = api.selectedScrollSnap()
  }

  api.on('select', syncSlide)
  api.on('reInit', syncSlide)
  nextTick(syncSlide)
}

const chipItems = computed(() =>
  slides.value.map((s) => ({ label: t(`preauth.landing.showcase.slides.${s.key}.title`) })),
)

// Sync chip/dot selection → carousel
watch(currentSlide, (index) => {
  carouselApi.value?.scrollTo(index)
})

function goToSlide(index: number) {
  currentSlide.value = index
}

const handleGetStarted = () => {
  if (authStore.isAuthenticated) {
    router.push({ name: 'home' })
    return
  }
  const redirectUri =
    import.meta.env.VITE_AUTH0_CALLBACK_URL || `${window.location.origin}/app/home`
  authStore.auth0.loginWithRedirect({
    authorizationParams: {
      redirect_uri: redirectUri,
    },
  })
}

const navigateToAbout = () => {
  router.push({ name: 'about' })
}
</script>

<template>
  <div class="space-y-20">
    <!-- Hero Section -->
    <div class="text-center space-y-8">
      <div class="space-y-4">
        <img :src="logo" alt="Logo" class="h-24 w-24 mx-auto rounded-xl" />
        <h1 data-testid="page-heading" class="text-4xl font-bold tracking-tight">{{ $t('preauth.landing.welcome') }}</h1>
        <p class="text-xl text-muted-foreground max-w-2xl mx-auto">
          {{ $t('preauth.landing.subtitle') }}
        </p>
        <p class="text-sm text-muted-foreground/70 italic max-w-xl mx-auto">
          {{ $t('preauth.landing.nameExplainer') }}
        </p>
      </div>

      <div class="space-y-4">
        <div class="flex flex-col sm:flex-row gap-4 justify-center items-center">
          <Button data-testid="btn-cta-primary" @click="handleGetStarted" size="lg" class="px-8 py-3 text-lg font-medium">
            {{
              authStore.isAuthenticated
                ? $t('preauth.layout.navigation.goToDashboard')
                : $t('preauth.landing.getStarted')
            }}
          </Button>
          <Button
            data-testid="btn-cta-secondary"
            @click="navigateToAbout"
            variant="outline"
            size="lg"
            class="px-8 py-3 text-lg font-medium"
          >
            {{ $t('preauth.landing.learnMore') }}
          </Button>
        </div>
        <p class="text-sm text-muted-foreground">{{ $t('preauth.landing.authNote') }}</p>
      </div>
    </div>

    <!-- Feature Cards -->
    <div data-testid="section-features" class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div class="p-6 border rounded-lg">
        <h3 class="text-lg font-semibold mb-2">
          {{ $t('preauth.landing.features.fastSecure.title') }}
        </h3>
        <p class="text-muted-foreground">
          {{ $t('preauth.landing.features.fastSecure.description') }}
        </p>
      </div>
      <div class="p-6 border rounded-lg">
        <h3 class="text-lg font-semibold mb-2">
          {{ $t('preauth.landing.features.easyToUse.title') }}
        </h3>
        <p class="text-muted-foreground">
          {{ $t('preauth.landing.features.easyToUse.description') }}
        </p>
      </div>
      <div class="p-6 border rounded-lg">
        <h3 class="text-lg font-semibold mb-2">
          {{ $t('preauth.landing.features.scalable.title') }}
        </h3>
        <p class="text-muted-foreground">
          {{ $t('preauth.landing.features.scalable.description') }}
        </p>
      </div>
    </div>

    <!-- Showcase Carousel Section -->
    <div data-testid="section-preview" class="space-y-8">
      <div class="text-center space-y-3">
        <Badge variant="secondary" class="text-sm px-3 py-1">Preview</Badge>
        <h2 class="text-3xl font-bold tracking-tight">
          {{ $t('preauth.landing.showcase.title') }}
        </h2>
        <p class="text-lg text-muted-foreground max-w-xl mx-auto">
          {{ $t('preauth.landing.showcase.subtitle') }}
        </p>
      </div>

      <!-- Slide Selector Pills -->
      <ChipNav v-model="currentSlide" :items="chipItems" variant="rounded" stretch />

      <!-- Carousel -->
      <div class="relative max-w-5xl mx-auto">
        <Carousel class="w-full" @init-api="onApiSet" :opts="{ loop: true }">
          <CarouselContent class="py-4">
            <CarouselItem v-for="slide in slides" :key="slide.key">
              <div class="space-y-4 px-8">
                <div class="relative overflow-hidden rounded-xl border bg-background shadow-2xl">
                  <div
                    class="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent z-10 pointer-events-none"
                  />
                  <img
                    :src="slide.image"
                    :alt="$t(`preauth.landing.showcase.slides.${slide.key}.title`)"
                    class="w-full h-auto"
                    loading="lazy"
                  />
                </div>
                <div class="text-center space-y-2 pb-2">
                  <h3 class="text-xl font-semibold">
                    {{ $t(`preauth.landing.showcase.slides.${slide.key}.title`) }}
                  </h3>
                  <p class="text-muted-foreground max-w-lg mx-auto">
                    {{ $t(`preauth.landing.showcase.slides.${slide.key}.description`) }}
                  </p>
                </div>
              </div>
            </CarouselItem>
          </CarouselContent>
          <CarouselPrevious class="-left-12 hidden lg:inline-flex" />
          <CarouselNext class="-right-12 hidden lg:inline-flex" />
        </Carousel>

        <!-- Dot indicators -->
        <div class="flex justify-center gap-2 mt-4">
          <button
            v-for="(slide, index) in slides"
            :key="slide.key"
            @click="goToSlide(index)"
            class="w-2 h-2 rounded-full transition-all duration-200"
            :class="
              currentSlide === index
                ? 'bg-primary w-6'
                : 'bg-muted-foreground/30 hover:bg-muted-foreground/50'
            "
          />
        </div>
      </div>
    </div>
  </div>
</template>
