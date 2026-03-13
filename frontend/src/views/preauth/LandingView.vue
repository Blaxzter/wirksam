<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from '@/components/ui/carousel'
import type { CarouselApi } from '@/components/ui/carousel'

import logo from '@/assets/logo/logo.svg'

const authStore = useAuthStore()
const router = useRouter()
const { locale } = useI18n()

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

const pillsContainer = ref<HTMLElement>()

function goToSlide(index: number) {
  carouselApi.value?.scrollTo(index)
  currentSlide.value = index
}

function scrollActivePillIntoView() {
  const container = pillsContainer.value
  if (!container) return
  const activeBtn = container.children[currentSlide.value] as HTMLElement | undefined
  if (!activeBtn) return
  const containerRect = container.getBoundingClientRect()
  const btnRect = activeBtn.getBoundingClientRect()
  if (btnRect.left < containerRect.left || btnRect.right > containerRect.right) {
    activeBtn.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }
}

watch(currentSlide, () => nextTick(scrollActivePillIntoView))

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
        <h1 class="text-4xl font-bold tracking-tight">{{ $t('preauth.landing.welcome') }}</h1>
        <p class="text-xl text-muted-foreground max-w-2xl mx-auto">
          {{ $t('preauth.landing.subtitle') }}
        </p>
      </div>

      <div class="space-y-4">
        <div class="flex flex-col sm:flex-row gap-4 justify-center items-center">
          <Button @click="handleGetStarted" size="lg" class="px-8 py-3 text-lg font-medium">
            {{
              authStore.isAuthenticated
                ? $t('preauth.layout.navigation.goToDashboard')
                : $t('preauth.landing.getStarted')
            }}
          </Button>
          <Button
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
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
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
    <div class="space-y-8">
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
      <div class="pills-wrapper relative overflow-hidden">
        <div class="pills-fade-left pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-background to-transparent" />
        <div class="pills-fade-right pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-background to-transparent" />
        <div
          ref="pillsContainer"
          class="flex gap-2 overflow-x-auto scroll-smooth px-8 no-scrollbar"
        >
          <button
            v-for="(slide, index) in slides"
            :key="slide.key"
            @click="goToSlide(index)"
            class="shrink-0 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200"
            :class="
              currentSlide === index
                ? 'bg-primary text-primary-foreground shadow-md'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            "
          >
            {{ $t(`preauth.landing.showcase.slides.${slide.key}.title`) }}
          </button>
        </div>
      </div>

      <!-- Carousel -->
      <div class="relative max-w-5xl mx-auto">
        <Carousel
          class="w-full"
          @init-api="onApiSet"
          :opts="{ loop: true }"
        >
          <CarouselContent class="py-4">
            <CarouselItem v-for="slide in slides" :key="slide.key">
              <div class="space-y-4 px-8">
                <div
                  class="relative overflow-hidden rounded-xl border bg-background shadow-2xl"
                >
                  <div
                    class="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent z-10 pointer-events-none"
                  />
                  <img
                    :src="slide.image"
                    :alt="$t(`preauth.landing.showcase.slides.${slide.key}.title`)"
                    class="w-full h-auto"
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

<style scoped>
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
</style>
