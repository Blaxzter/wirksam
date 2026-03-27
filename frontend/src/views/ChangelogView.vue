<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAdaptiveCarouselHeight } from '@/composables/useAdaptiveCarouselHeight'
import { useChangelogStatus } from '@/composables/useChangelogStatus'

import type { UnwrapRefCarouselApi } from '@/components/ui/carousel/interface'

import { Badge } from '@/components/ui/badge'
import { Carousel, CarouselContent, CarouselItem } from '@/components/ui/carousel'
import {
  Dialog,
  DialogScrollContent,
  DialogTitle,
} from '@/components/ui/dialog'

import ChipNav from '@/components/utils/ChipNav.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const { isNewVersion, markAsSeen } = useChangelogStatus()

onMounted(markAsSeen)

// ── Lightbox ──
const lightboxSrc = ref('')
const lightboxAlt = ref('')
const lightboxOpen = ref(false)

function onContentClick(e: MouseEvent) {
  const img = (e.target as HTMLElement).closest('img')
  if (!img) return
  lightboxSrc.value = img.src
  lightboxAlt.value = img.alt || ''
  lightboxOpen.value = true
}

// ── Changelog data ──
import enChangelog from '../changelog/generated/en.json'
import deChangelog from '../changelog/generated/de.json'

const generatedEntries: Record<string, { title: string; version: string; date: string; html: string }[]> = {
  en: enChangelog,
  de: deChangelog,
}

const rawImages = import.meta.glob('../changelog/images/**/*', {
  eager: true,
  import: 'default',
}) as Record<string, string>

const imagesByLocale: Record<string, Record<string, string>> = {}
for (const [path, url] of Object.entries(rawImages)) {
  const parts = path.split('/')
  const filename = parts.pop()!
  const loc = parts.pop()!
  if (!imagesByLocale[loc]) imagesByLocale[loc] = {}
  imagesByLocale[loc][filename] = url
}

function resolveImagePaths(html: string, loc: string): string {
  const localeImages = imagesByLocale[loc] ?? {}
  const fallbackImages = imagesByLocale.de ?? {}
  return html.replace(/<img\s+src="\.\/images\/([^"]+)"\s+alt="([^"]*)"/g, (_, filename, alt) => {
    const resolved = localeImages[filename] ?? fallbackImages[filename]
    const src = resolved ?? `./images/${filename}`
    return `<img src="${src}" alt="${alt}" role="img" aria-label="${alt}" loading="lazy"`
  })
}

interface ChangelogEntry {
  title: string
  version: string
  date: Date
  html: string
}

const entries = computed<ChangelogEntry[]>(() => {
  const localized = generatedEntries[locale.value] ?? []
  const fallback = generatedEntries.en ?? []

  const byVersion = new Map<string, { title: string; version: string; date: string; html: string }>()
  for (const entry of fallback) byVersion.set(entry.version, entry)
  for (const entry of localized) byVersion.set(entry.version, entry)

  return Array.from(byVersion.values())
    .map((e) => ({
      title: e.title,
      version: e.version,
      date: new Date(e.date),
      html: resolveImagePaths(e.html, locale.value),
    }))
    .sort((a, b) => b.date.getTime() - a.date.getTime())
})

function formatDateLong(date: Date): string {
  return date.toLocaleString(locale.value, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Chip items for mobile ──
const chipItems = computed(() =>
  entries.value.map((e, i) => ({
    label: i === 0 ? `v${e.version} (${t('changelog.latest')})` : `v${e.version}`,
  })),
)

// ── Route-synced state ──
function versionToIndex(version: string | undefined): number {
  if (!version) return 0
  const idx = entries.value.findIndex((e) => e.version === version)
  return idx !== -1 ? idx : 0
}

const activeIndex = computed({
  get: () => versionToIndex(route.params.version as string | undefined),
  set: (index: number) => {
    const version = entries.value[index]?.version
    router.replace({ name: 'changelog', params: { version: index === 0 ? undefined : version } })
  },
})

const desktopSelected = computed(() => entries.value[activeIndex.value])

// ── Mobile carousel state ──
const mobileSlide = ref(activeIndex.value)
const carouselApi = ref<UnwrapRefCarouselApi>()
useAdaptiveCarouselHeight(carouselApi)

function onCarouselInit(api: UnwrapRefCarouselApi) {
  carouselApi.value = api
  api.on('select', () => {
    const index = api.selectedScrollSnap()
    mobileSlide.value = index
    if (index !== activeIndex.value) {
      activeIndex.value = index
    }
  })
}

// Sync chip taps → carousel + route
watch(mobileSlide, (index) => {
  carouselApi.value?.scrollTo(index)
  if (index !== activeIndex.value) {
    activeIndex.value = index
  }
})

// Sync route changes → mobile carousel
watch(activeIndex, (index) => {
  if (index !== mobileSlide.value) {
    mobileSlide.value = index
  }
})
</script>

<template>
  <div>
    <!-- Header — always centered -->
    <div class="mx-auto max-w-3xl pb-2">
      <h1 class="text-3xl font-bold">{{ t('changelog.title') }}</h1>
      <p class="text-muted-foreground mt-2">{{ t('changelog.subtitle') }}</p>
    </div>

    <!-- ==================== MOBILE / TABLET (<xl) ==================== -->
    <div class="xl:hidden">
      <ChipNav v-model="mobileSlide" :items="chipItems" class="mb-4" />

      <div class="mx-auto max-w-3xl">
        <Carousel class="w-full" @init-api="onCarouselInit" :opts="{ watchDrag: true }">
          <CarouselContent class="items-start">
            <CarouselItem
              v-for="entry in entries"
              :key="entry.version"
              class="basis-full"
            >
              <div>
                <div class="space-y-1 mb-4">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="text-xl font-semibold">{{ entry.title }}</h2>
                    <Badge
                      v-if="entry.version === entries[0]?.version"
                      variant="default"
                      class="text-[10px]"
                    >
                      {{ t('changelog.latest') }}
                    </Badge>
                  </div>
                  <div class="flex items-center gap-2 text-sm text-muted-foreground">
                    <span>v{{ entry.version }}</span>
                    <span>&middot;</span>
                    <time>{{ formatDateLong(entry.date) }}</time>
                  </div>
                </div>
                <div class="changelog-content" v-html="entry.html" @click="onContentClick" />
              </div>
            </CarouselItem>
          </CarouselContent>
        </Carousel>
      </div>
    </div>

    <!-- ==================== DESKTOP (xl+) ==================== -->
    <div class="hidden xl:grid grid-cols-[1fr_48rem_1fr] mt-8">
      <!-- Nav in left gutter -->
      <div class="flex justify-end pr-8">
        <nav class="w-44 sticky top-8 self-start">
          <div class="rounded-lg border p-2 space-y-0.5">
            <button
              v-for="(entry, index) in entries"
              :key="entry.version"
              class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors"
              :class="
                activeIndex === index
                  ? 'bg-accent text-accent-foreground font-medium'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
              "
              @click="activeIndex = index"
            >
              <span
                class="size-1.5 shrink-0 rounded-full"
                :class="index === 0 ? 'bg-primary' : 'bg-border'"
              />
              <span class="truncate flex-1">v{{ entry.version }}</span>
              <span
                v-if="isNewVersion(entry.version)"
                class="size-1.5 shrink-0 rounded-full bg-primary"
              />
            </button>
          </div>
        </nav>
      </div>

      <!-- Content -->
      <div v-if="desktopSelected">
        <div class="space-y-1 mb-4">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-xl font-semibold">{{ desktopSelected.title }}</h2>
            <Badge
              v-if="desktopSelected.version === entries[0]?.version"
              variant="default"
              class="text-[10px]"
            >
              {{ t('changelog.latest') }}
            </Badge>
          </div>
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <span>v{{ desktopSelected.version }}</span>
            <span>&middot;</span>
            <time>{{ formatDateLong(desktopSelected.date) }}</time>
          </div>
        </div>

        <div class="changelog-content" v-html="desktopSelected.html" @click="onContentClick" />
      </div>

      <!-- Right spacer for symmetry -->
      <div aria-hidden="true" />
    </div>

    <!-- Image lightbox -->
    <Dialog v-model:open="lightboxOpen">
      <DialogScrollContent class="max-w-4xl p-2">
        <DialogTitle class="sr-only">{{ lightboxAlt }}</DialogTitle>
        <img
          :src="lightboxSrc"
          :alt="lightboxAlt"
          class="w-full rounded-md"
        />
      </DialogScrollContent>
    </Dialog>
  </div>
</template>

<style scoped>
.changelog-content :deep(h2) {
  font-size: 1.125rem;
  font-weight: 600;
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
}

.changelog-content :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}

.changelog-content :deep(p) {
  color: var(--muted-foreground);
  margin-bottom: 0.75rem;
  line-height: 1.625;
}

.changelog-content :deep(ul) {
  list-style-type: disc;
  padding-left: 1.25rem;
  margin-bottom: 0.75rem;
}

.changelog-content :deep(ul li) {
  color: var(--muted-foreground);
  margin-bottom: 0.25rem;
  line-height: 1.625;
}

.changelog-content :deep(img) {
  border-radius: var(--radius);
  border: 1px solid var(--border);
  margin-top: 1rem;
  margin-bottom: 1rem;
  max-width: 22rem;
  max-height: 20rem;
  width: 100%;
  object-fit: cover;
  object-position: top;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  cursor: zoom-in;
  transition: box-shadow 0.2s;
}

.changelog-content :deep(img:hover) {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
}

.changelog-content :deep(a) {
  color: var(--primary);
  text-decoration: underline;
}

.changelog-content :deep(code) {
  font-size: 0.875rem;
  background: var(--muted);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-sm);
}
</style>
