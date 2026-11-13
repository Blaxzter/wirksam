<template>
  <!-- Define section content once, reuse in both mobile and desktop layouts -->
  <DefineSectionContent v-slot="{ id }">
    <div class="space-y-6" :data-testid="`section-${id}`">
      <template v-if="id === 'profile'">
        <CurrentProfileCard :user="user" />
        <EditProfileForm :user="user" @profile-updated="handleProfileUpdated" />
      </template>

      <template v-if="id === 'security'">
        <ChangePasswordCard />
        <ActiveSessionsCard />
      </template>

      <template v-if="id === 'event'">
        <ActiveEventCard />
      </template>

      <template v-if="id === 'notifications'">
        <NotificationSettingsCard />
      </template>

      <template v-if="id === 'calendar'">
        <CalendarSyncCard />
      </template>

      <template v-if="id === 'language'">
        <LanguageSettingsCard />
        <TimeFormatCard />
      </template>

      <template v-if="id === 'appearance'">
        <AppearanceCard />
      </template>

      <template v-if="id === 'dataPrivacy'">
        <DataExportCard />
        <DeleteAccountCard />
      </template>
    </div>
  </DefineSectionContent>

  <div :class="{ 'grid grid-cols-[1fr_48rem_1fr] gap-y-8': isDesktop }">
    <!-- Header -->
    <div :class="isDesktop ? 'col-start-2 pb-2' : 'mx-auto max-w-3xl pb-2'">
      <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold tracking-tight">
        {{ $t('user.settings.title') }}
      </h1>
      <p class="text-muted-foreground mt-2">
        {{ $t('user.settings.subtitle') }}
      </p>
    </div>

    <!-- ==================== MOBILE / TABLET (<xl) ==================== -->
    <div v-if="!isDesktop">
      <!-- Pinned under the top bar: a section can run long, and the pills are
           the only way to the next one besides swiping. -->
      <StickyPageBar class="mb-4">
        <ChipNav v-model="mobileSlide" :items="chipItems" />
      </StickyPageBar>

      <div class="mx-auto max-w-3xl">
        <Carousel class="w-full" @init-api="onCarouselInit" :opts="{ watchDrag: true }">
          <CarouselContent class="items-start">
            <CarouselItem v-for="item in visibleNavItems" :key="item.id" class="basis-full">
              <SectionContent :id="item.id" />
            </CarouselItem>
          </CarouselContent>
        </Carousel>
      </div>
    </div>

    <!-- ==================== DESKTOP (xl+) ==================== -->
    <template v-if="isDesktop">
      <!-- Nav in left gutter -->
      <div class="row-start-2 flex justify-end pr-8">
        <nav
          class="w-44 sticky top-[calc(var(--demo-banner-height,0px)+var(--app-header-height,4rem)+2rem)] self-start space-y-1"
        >
          <button
            v-for="item in visibleNavItems"
            :key="item.id"
            @click="activeSection = item.id"
            class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors text-left"
            :class="[
              activeSection === item.id
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground',
            ]"
          >
            <component :is="item.icon" class="h-4 w-4 shrink-0" />
            {{ item.label }}
          </button>
        </nav>
      </div>

      <!-- Content -->
      <div class="row-start-2">
        <SectionContent :id="activeSection" />
      </div>

      <!-- Right spacer for symmetry -->
      <div class="row-start-2" aria-hidden="true" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { type Component, computed, ref, watch } from 'vue'

import {
  Bell,
  CalendarDays,
  CalendarRange,
  GlobeIcon,
  KeyRound,
  Palette as PaletteIcon,
  ShieldIcon,
  UserIcon,
} from '@lucide/vue'
import { createReusableTemplate, useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAdaptiveCarouselHeight } from '@/composables/useAdaptiveCarouselHeight'

import { Carousel, CarouselContent, CarouselItem } from '@/components/ui/carousel'
import type { UnwrapRefCarouselApi } from '@/components/ui/carousel/interface'

import ActiveEventCard from '@/components/account/user/ActiveEventCard.vue'
import ActiveSessionsCard from '@/components/account/user/ActiveSessionsCard.vue'
import AppearanceCard from '@/components/account/user/AppearanceCard.vue'
import CalendarSyncCard from '@/components/account/user/CalendarSyncCard.vue'
import ChangePasswordCard from '@/components/account/user/ChangePasswordCard.vue'
import CurrentProfileCard from '@/components/account/user/CurrentProfileCard.vue'
import DataExportCard from '@/components/account/user/DataExportCard.vue'
import DeleteAccountCard from '@/components/account/user/DeleteAccountCard.vue'
import EditProfileForm from '@/components/account/user/EditProfileForm.vue'
import LanguageSettingsCard from '@/components/account/user/LanguageSettingsCard.vue'
import NotificationSettingsCard from '@/components/account/user/NotificationSettingsCard.vue'
import TimeFormatCard from '@/components/account/user/TimeFormatCard.vue'
import StickyPageBar from '@/components/layout/StickyPageBar.vue'
import ChipNav from '@/components/utils/ChipNav.vue'

interface NavItem {
  id: string
  label: string
  icon: Component
}

// Store & router
const authStore = useAuthStore()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const isDesktop = useMediaQuery('(min-width: 1280px)')

const [DefineSectionContent, SectionContent] = createReusableTemplate<{ id: string }>()

// Computed properties
const user = computed(() => authStore.user)

// Navigation items
const navItems = computed<NavItem[]>(() => [
  { id: 'profile', label: t('user.settings.nav.profile'), icon: UserIcon },
  { id: 'security', label: t('user.settings.nav.security'), icon: KeyRound },
  { id: 'event', label: t('user.settings.nav.event'), icon: CalendarRange },
  { id: 'notifications', label: t('user.settings.nav.notifications'), icon: Bell },
  { id: 'calendar', label: t('user.settings.nav.calendar'), icon: CalendarDays },
  { id: 'language', label: t('user.settings.nav.language'), icon: GlobeIcon },
  { id: 'appearance', label: t('user.settings.nav.appearance'), icon: PaletteIcon },
  { id: 'dataPrivacy', label: t('user.settings.nav.dataPrivacy'), icon: ShieldIcon },
])

// Every section is available to every account now that passwords are ours: the
// Security section used to be gated on the identity provider, read once and
// never re-read, so it vanished for anyone whose user object had not loaded by
// the time this component was created.
const visibleNavItems = computed(() => navItems.value)

const chipItems = computed(() =>
  visibleNavItems.value.map((item) => ({ label: item.label, icon: item.icon })),
)

// ── Section from route ──
const validSectionIds = computed(() => visibleNavItems.value.map((item) => item.id))

const activeSection = computed({
  get: () => {
    const param = route.params.section as string | undefined
    if (param && validSectionIds.value.includes(param)) return param
    return 'profile'
  },
  set: (id: string) => {
    router.replace({ name: 'settings', params: { section: id === 'profile' ? undefined : id } })
  },
})

// ── Mobile carousel state ──
const mobileSlide = ref(validSectionIds.value.indexOf(activeSection.value))
const carouselApi = ref<UnwrapRefCarouselApi>()
useAdaptiveCarouselHeight(carouselApi)

function onCarouselInit(api: UnwrapRefCarouselApi) {
  carouselApi.value = api
  if (!api) return
  // Scroll to initial position for deep-linked sections
  if (mobileSlide.value > 0) {
    api.scrollTo(mobileSlide.value, true)
  }
  api.on('select', () => {
    const index = api.selectedScrollSnap()
    mobileSlide.value = index
    const sectionId = visibleNavItems.value[index]?.id
    if (sectionId && sectionId !== activeSection.value) {
      activeSection.value = sectionId
    }
  })
}

// Sync chip taps → carousel + route
watch(mobileSlide, (index) => {
  carouselApi.value?.scrollTo(index)
  const sectionId = visibleNavItems.value[index]?.id
  if (sectionId && sectionId !== activeSection.value) {
    activeSection.value = sectionId
  }
})

// Sync route changes → mobile carousel
watch(activeSection, (id) => {
  const index = validSectionIds.value.indexOf(id)
  if (index !== -1 && index !== mobileSlide.value) {
    mobileSlide.value = index
  }
})

// Handle profile updated task
const handleProfileUpdated = async (values: Record<string, unknown>) => {
  authStore.updateUser({
    ...authStore.user,
    ...values,
  })
}
</script>
