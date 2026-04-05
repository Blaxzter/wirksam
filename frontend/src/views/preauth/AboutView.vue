<script setup lang="ts">
import { computed } from 'vue'

import { ArrowLeftIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'

import { getTranslationList } from '@/lib/utils'

const router = useRouter()
const { t } = useI18n()

const goBackToHome = () => {
  router.push({ name: 'landing' })
}

// Create arrays from numbered translation keys using utility function
const frontendItems = computed(() =>
  getTranslationList(t, 'preauth.about.sections.techStack.frontend.items'),
)

const backendItems = computed(() =>
  getTranslationList(t, 'preauth.about.sections.techStack.backend.items'),
)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-3xl font-bold">{{ $t('preauth.about.title') }}</h1>
        <p class="text-muted-foreground">
          {{ $t('preauth.about.subtitle') }}
        </p>
      </div>
      <Button data-testid="btn-back" @click="goBackToHome" variant="ghost" size="sm" class="gap-2">
        <ArrowLeftIcon class="h-4 w-4" />
        {{ $t('preauth.about.backToHome') }}
      </Button>
    </div>

    <div class="space-y-8">
      <section class="space-y-4">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.about.sections.techStack.title') }}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="p-6 border rounded-lg">
            <h3 class="text-lg font-semibold mb-2">
              {{ $t('preauth.about.sections.techStack.frontend.title') }}
            </h3>
            <ul class="space-y-1 text-muted-foreground">
              <li v-for="item in frontendItems" :key="item">• {{ item }}</li>
            </ul>
          </div>
          <div class="p-6 border rounded-lg">
            <h3 class="text-lg font-semibold mb-2">
              {{ $t('preauth.about.sections.techStack.backend.title') }}
            </h3>
            <ul class="space-y-1 text-muted-foreground">
              <li v-for="item in backendItems" :key="item">• {{ item }}</li>
            </ul>
          </div>
        </div>
      </section>

      <section class="space-y-4">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.about.sections.features.title') }}</h2>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="p-4 border rounded-lg">
            <h3 class="font-semibold mb-2">
              {{ $t('preauth.about.sections.features.authentication.title') }}
            </h3>
            <p class="text-sm text-muted-foreground">
              {{ $t('preauth.about.sections.features.authentication.description') }}
            </p>
          </div>
          <div class="p-4 border rounded-lg">
            <h3 class="font-semibold mb-2">
              {{ $t('preauth.about.sections.features.responsiveDesign.title') }}
            </h3>
            <p class="text-sm text-muted-foreground">
              {{ $t('preauth.about.sections.features.responsiveDesign.description') }}
            </p>
          </div>
          <div class="p-4 border rounded-lg">
            <h3 class="font-semibold mb-2">
              {{ $t('preauth.about.sections.features.apiIntegration.title') }}
            </h3>
            <p class="text-sm text-muted-foreground">
              {{ $t('preauth.about.sections.features.apiIntegration.description') }}
            </p>
          </div>
        </div>
      </section>

      <section class="space-y-4">
        <h2 class="text-2xl font-semibold">{{ $t('preauth.about.sections.development.title') }}</h2>
        <div class="p-6 border rounded-lg">
          <p class="text-muted-foreground mb-4">
            {{ $t('preauth.about.sections.development.description') }}
          </p>
          <div class="flex flex-wrap gap-2">
            <span class="px-3 py-1 bg-primary/10 text-primary text-sm rounded-full"
              >TypeScript</span
            >
            <span class="px-3 py-1 bg-primary/10 text-primary text-sm rounded-full">Vue 3</span>
            <span class="px-3 py-1 bg-primary/10 text-primary text-sm rounded-full">FastAPI</span>
            <span class="px-3 py-1 bg-primary/10 text-primary text-sm rounded-full">Docker</span>
            <span class="px-3 py-1 bg-primary/10 text-primary text-sm rounded-full">Auth0</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped></style>
