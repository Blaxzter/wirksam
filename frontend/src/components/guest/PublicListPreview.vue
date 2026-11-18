<script setup lang="ts">
/**
 * A shared list's public page as helpers see it right now, framed like a
 * phone, for the organisers' "So sehen es Helfende" tab.
 *
 * Read-only: the shifts carry no buttons, and one line says that signing up
 * happens through the link. A paused or closed list shows what helpers see
 * instead. It is a picture of another page, so nothing in it is a heading: the
 * management page's outline stays its own.
 */
import { computed } from 'vue'

import { CirclePauseIcon, LockIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import GuestStateMessage from '@/components/guest/GuestStateMessage.vue'
import PublicListHeader from '@/components/guest/PublicListHeader.vue'
import PublicShiftList from '@/components/guest/PublicShiftList.vue'

import type { PublicSharedList } from '@/client/types.gen'
import { sharedListUrl } from '@/lib/shared-lists'

const props = defineProps<{ list: PublicSharedList }>()

const { t } = useI18n()

/** The address bar of the frame: the link without its scheme, as a phone shows it. */
const address = computed(() => sharedListUrl(props.list.code).replace(/^https?:\/\//, ''))
</script>

<template>
  <figure
    class="mx-auto w-full max-w-md overflow-hidden rounded-[2rem] border-8 border-foreground/85 bg-background shadow-lg"
    data-testid="public-list-preview"
  >
    <figcaption class="sr-only">{{ t('guestSignup.preview.label') }}</figcaption>
    <p
      class="truncate bg-hero px-3 py-1.5 text-center font-mono text-xs text-hero-foreground"
      aria-hidden="true"
    >
      {{ address }}
    </p>
    <div class="space-y-4 p-4">
      <PublicListHeader :list="list" heading-tag="p" />

      <GuestStateMessage
        v-if="list.status === 'paused'"
        :icon="CirclePauseIcon"
        heading-tag="p"
        :title="t('guestSignup.states.paused.title')"
        :text="t('guestSignup.states.paused.text')"
        data-testid="public-list-preview-paused"
      />
      <GuestStateMessage
        v-else-if="list.status === 'closed'"
        :icon="LockIcon"
        heading-tag="p"
        :title="t('guestSignup.states.closed.title')"
        :text="t('guestSignup.states.closed.text')"
        data-testid="public-list-preview-closed"
      />
      <template v-else>
        <p class="text-sm text-muted-foreground" data-testid="public-list-preview-hint">
          {{ t('guestSignup.preview.hint') }}
        </p>
        <PublicShiftList
          v-if="list.days.length > 0"
          :days="list.days"
          :show-names="list.show_names === 'first'"
          readonly
          day-heading-tag="p"
        />
        <p v-else class="text-sm text-muted-foreground">{{ t('guestSignup.states.empty') }}</p>
      </template>
    </div>
  </figure>
</template>
