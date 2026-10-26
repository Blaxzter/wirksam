<script setup lang="ts">
import { computed } from 'vue'

import { ExternalLink, FileText } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthedImage } from '@/composables/useAuthedImage'

import { Skeleton } from '@/components/ui/skeleton'

import type { TeamDocumentRead } from '@/client/types.gen'

/**
 * A file attached to a join request, shown next to the check it is for.
 *
 * The file needs the bearer token, so it is fetched as a blob (like venue
 * plans) and handed to `<img>` or a link as an object URL; the server sends it
 * `no-store`, and the URL is revoked when the dialog closes.
 */
const props = defineProps<{
  eventId: string
  teamId: string
  userId: string
  document: TeamDocumentRead
}>()

const { t } = useI18n()

const url = computed(
  () =>
    `${import.meta.env.VITE_API_URL}/events/${props.eventId}/teams/${props.teamId}` +
    `/members/${props.userId}/documents/${props.document.requirement_id}`,
)
const isImage = computed(() => props.document.content_type.startsWith('image/'))

const { src, loading, error } = useAuthedImage(url)

const sizeLabel = computed(() => {
  const kb = props.document.size / 1024
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(kb))} KB`
})
</script>

<template>
  <div class="space-y-1.5" data-testid="team-document-preview">
    <Skeleton v-if="loading" class="h-24 w-full" />
    <p v-else-if="error" class="text-destructive text-xs" role="alert">
      {{ t('teams.review.fileFailed') }}
    </p>
    <a
      v-else-if="src && isImage"
      :href="src"
      target="_blank"
      rel="noopener"
      class="block overflow-hidden rounded-md border"
      :aria-label="t('teams.review.openFileNamed', { name: document.filename })"
    >
      <img :src="src" :alt="document.filename" class="max-h-56 w-full bg-muted object-contain" />
    </a>
    <a
      v-if="src"
      :href="src"
      target="_blank"
      rel="noopener"
      class="text-primary inline-flex max-w-full items-center gap-1.5 text-xs underline-offset-2 hover:underline"
      data-testid="team-document-open"
    >
      <FileText v-if="!isImage" class="size-3.5 shrink-0" />
      <span class="truncate">{{ document.filename }}</span>
      <span class="text-muted-foreground shrink-0">({{ sizeLabel }})</span>
      <ExternalLink class="size-3 shrink-0" />
    </a>
  </div>
</template>
