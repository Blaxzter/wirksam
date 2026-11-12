<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { ArrowRightIcon, CheckIcon, ChevronDownIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { ScreenshotItem } from '@/composables/useScreenshotSource'

import ContentPageShell from '@/components/content/ContentPageShell.vue'
import DocBlocks from '@/components/content/DocBlocks.vue'
import DocDeviceToggle from '@/components/content/DocDeviceToggle.vue'
import LandingSection from '@/components/landing/LandingSection.vue'
import ScreenshotLightbox from '@/components/landing/ScreenshotLightbox.vue'
import SectionHeading from '@/components/landing/SectionHeading.vue'

import {
  ACCENT_COLORS,
  type DocPage,
  docAccent,
  docId,
  docPageById,
  docRouteName,
  pageLook,
} from '@/lib/content-pages'
import { DEVICE_KEY, offersChoice, preferredDevice, shotDevice, shotFile } from '@/lib/doc-shots'
import type { DocBlock, DocDevice, DocShot } from '@/lib/doc-types'
import { docFor, loadDoc } from '@/lib/docs-content'

/**
 * One feature page or guide. The route passes the page's id, and all of the text
 * comes from its Markdown in `src/docs/`. A guide's sections are numbered steps,
 * which the prerender mirrors into HowTo JSON-LD, and the FAQ into FAQPage.
 */
const props = defineProps<{ id: string }>()

const { t, locale } = useI18n()
const router = useRouter()

const page = computed(() => docPageById(props.id)!)
// The route loaded this page in the language it opened in. Switching language
// here fetches the other copy, and `docFor` keeps the old one up until it's in.
watch([() => props.id, locale], ([id, language]) => void loadDoc(id, language), {
  immediate: true,
})
const doc = computed(() => docFor(props.id, locale.value)!)
const isGuide = computed(() => page.value.kind === 'guide')
const hub = computed(() => (isGuide.value ? 'guides' : 'features'))

const look = computed(() => pageLook(props.id))

// Each page to read next keeps its own colour, so it looks the same here as on
// the overview.
const related = computed(() =>
  doc.value.related
    .map(docPageById)
    .filter((item): item is DocPage => Boolean(item))
    .map((item) => ({ page: item, color: ACCENT_COLORS[docAccent(docId(item))] })),
)

// Every screenshot on the page in order, so the viewer can page between them.
const shots = computed<DocShot[]>(() =>
  [doc.value.intro, ...doc.value.sections.map((section) => section.blocks)]
    .flat()
    .flatMap((block: DocBlock) => (block.type === 'shots' ? block.shots : [])),
)

// Screenshots from a computer or from a phone. The prerendered page shows the
// computer's; a visitor then gets what they chose last time, or else what they
// are reading on.
const device = ref<DocDevice>('desktop')
const offersDevices = computed(() => offersChoice(shots.value))

onMounted(() => {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(DEVICE_KEY)
  } catch {
    // Storage can be off. The choice is then only for this visit.
  }
  device.value = preferredDevice(stored, window.matchMedia('(max-width: 767px)').matches)
})

function chooseDevice(value: DocDevice) {
  device.value = value
  try {
    localStorage.setItem(DEVICE_KEY, value)
  } catch {
    // As above.
  }
}

const gallery = computed<ScreenshotItem[]>(() =>
  shots.value.map((shot) => {
    const shown = shotDevice(shot, device.value)
    return {
      name: shotFile(shot.name, shown),
      alt: shot.alt,
      caption: shot.alt,
      phone: shown === 'phone',
      marks: shot.devices[shown],
    }
  }),
)
const zoomed = ref<number | null>(null)

function zoom(shot: DocShot) {
  zoomed.value = shots.value.indexOf(shot)
}

// The links in the Markdown are plain anchors, which is what a crawler needs.
// A click on one stays in the app instead of reloading it.
function onBodyClick(event: MouseEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const link = (event.target as HTMLElement).closest('a')
  const href = link?.getAttribute('href')
  if (!href?.startsWith('/') || link?.target) return
  event.preventDefault()
  router.push(href)
}
</script>

<template>
  <ContentPageShell
    :eyebrow="t(`preauth.docs.hubs.${page.kind}.eyebrow`)"
    :title="doc.title"
    :lede="doc.lede"
    :breadcrumb="t(`preauth.docs.pages.${page.key}.name`)"
    :parent="{ routeName: hub, label: t(`preauth.docs.hubs.${page.kind}.breadcrumb`) }"
    :hide-actions="isGuide"
    :cta-title="t('preauth.docs.ctaTitle')"
    :art="look.art"
    :color="look.color"
  >

    <LandingSection id="content" width="wide">
      <!-- The page in three lines, for someone who reads no further. -->
      <section
        v-if="doc.points.length"
        aria-labelledby="in-short"
        data-testid="doc-points"
        class="mb-14 rounded-2xl border border-(--art)/35 bg-(--art)/10 p-5 sm:p-6"
      >
        <h2
          id="in-short"
          class="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground"
        >
          {{ t('preauth.docs.inShort') }}
        </h2>
        <ul class="mt-4 grid gap-4 sm:grid-cols-3 sm:gap-6">
          <li v-for="point in doc.points" :key="point" class="flex items-start gap-3">
            <span
              class="flex size-7 shrink-0 items-center justify-center rounded-full bg-(--art)/30"
              aria-hidden="true"
            >
              <CheckIcon class="size-4 text-foreground" />
            </span>
            <span class="pt-0.5 font-medium leading-snug">{{ point }}</span>
          </li>
        </ul>
      </section>

      <div class="lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-12" @click="onBodyClick">
        <article class="min-w-0" data-testid="doc-body">
          <!-- Beside the contents on a wide screen, above the text otherwise. -->
          <DocDeviceToggle
            v-if="offersDevices"
            :model-value="device"
            data-testid="doc-device"
            class="mb-10"
            :class="{ 'lg:hidden': doc.sections.length > 1 }"
            @update:model-value="chooseDevice"
          />
          <DocBlocks :blocks="doc.intro" :device="device" @zoom="zoom" />

          <!-- An ordered list in a guide: the numbers carry meaning, and screen
               readers say so. -->
          <component
            :is="isGuide ? 'ol' : 'div'"
            class="space-y-12"
            :class="{ 'mt-12': doc.intro.length > 0 }"
          >
            <component
              :is="isGuide ? 'li' : 'section'"
              v-for="(section, index) in doc.sections"
              :id="section.id"
              :key="section.id"
              class="scroll-mt-24"
            >
              <h2 class="flex items-center gap-3 text-2xl font-semibold tracking-tight">
                <span
                  v-if="isGuide"
                  class="flex size-9 shrink-0 items-center justify-center rounded-full bg-(--art)/25 text-sm font-bold text-foreground ring-2 ring-(--art)"
                  aria-hidden="true"
                >
                  {{ index + 1 }}
                </span>
                <span
                  v-else
                  class="h-7 w-1.5 shrink-0 rounded-full bg-(--art)"
                  aria-hidden="true"
                />
                {{ section.title }}
              </h2>
              <div class="mt-4">
                <DocBlocks :blocks="section.blocks" :device="device" @zoom="zoom" />
              </div>
            </component>
          </component>
        </article>

        <div
          v-if="doc.sections.length > 1"
          class="sticky top-24 hidden self-start text-sm lg:block"
        >
          <nav :aria-label="t('preauth.docs.onThisPage')">
            <p class="font-semibold">{{ t('preauth.docs.onThisPage') }}</p>
            <ul class="mt-3 space-y-2 border-l-2 border-(--art)/50 pl-3">
              <li v-for="section in doc.sections" :key="section.id">
                <a
                  :href="`#${section.id}`"
                  class="block leading-snug text-muted-foreground transition-colors hover:text-foreground"
                >
                  {{ section.title }}
                </a>
              </li>
            </ul>
          </nav>
          <DocDeviceToggle
            v-if="offersDevices"
            :model-value="device"
            class="mt-8"
            @update:model-value="chooseDevice"
          />
        </div>
      </div>
      <ScreenshotLightbox v-model:index="zoomed" :items="gallery" />
    </LandingSection>

    <LandingSection v-if="doc.faq.length" id="faq" tone="accent">
      <SectionHeading :title="t('preauth.docs.faqTitle')" />
      <!-- Native <details>, like LandingFaq: every answer stays in the prerendered
           HTML that search engines and LLM crawlers read. -->
      <div class="mx-auto mt-10 max-w-3xl divide-y rounded-2xl border bg-card shadow-sm">
        <details v-for="item in doc.faq" :id="item.id" :key="item.id" class="group scroll-mt-24">
          <summary
            class="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5 text-left font-semibold [&::-webkit-details-marker]:hidden"
          >
            <h3 class="text-base">{{ item.question }}</h3>
            <ChevronDownIcon
              class="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <div class="px-6 pb-3" @click="onBodyClick">
            <DocBlocks :blocks="[{ type: 'html', html: item.html }]" />
          </div>
        </details>
      </div>
    </LandingSection>

    <LandingSection id="read-on">
      <h2 class="text-center text-2xl font-bold tracking-tight">
        {{ t('preauth.docs.readOn') }}
      </h2>
      <ul class="mx-auto mt-8 grid max-w-3xl gap-4 sm:grid-cols-2">
        <li v-for="{ page: item, color } in related" :key="item.key" :style="{ '--art': color }">
          <RouterLink
            :to="{ name: docRouteName(item) }"
            :data-testid="`doc-related-${item.key}`"
            class="group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-5 pl-6 shadow-sm transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <span class="absolute inset-y-0 left-0 w-1.5 bg-(--art)" aria-hidden="true" />
            <span class="flex items-center justify-between gap-3 font-semibold">
              {{ t(`preauth.docs.pages.${item.key}.name`) }}
              <ArrowRightIcon
                class="size-4 shrink-0 text-primary transition-transform group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </span>
            <span class="mt-2 text-sm leading-relaxed text-muted-foreground">
              {{ t(`preauth.seo.${item.key}.description`) }}
            </span>
          </RouterLink>
        </li>
      </ul>
      <p class="mt-6 text-center">
        <RouterLink
          :to="{ name: hub }"
          data-testid="doc-hub-link"
          class="text-sm font-medium text-primary underline underline-offset-2"
        >
          {{ t(`preauth.docs.hubs.${page.kind}.all`) }}
        </RouterLink>
      </p>
    </LandingSection>
  </ContentPageShell>
</template>
