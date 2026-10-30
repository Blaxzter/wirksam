<script setup lang="ts">
import { computed } from 'vue'

import { UserCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Badge from '@/components/ui/badge/Badge.vue'

import { joinNames } from '@/components/events/teams/teamHelpers'

import type { TaskManagerBrief } from '@/client/types.gen'
import { initials } from '@/lib/format'

/**
 * "In charge: Anna and Ben" in a task's info row, with their avatars. The
 * caller hides it when nobody is in charge. A person in charge who is not an
 * organiser also gets a badge, so they can tell why they see the edit buttons.
 */
const props = defineProps<{
  managers: TaskManagerBrief[]
  /** The viewer is one of them and not an organiser of the event. */
  youAreInCharge?: boolean
}>()

const { t, locale } = useI18n()

/** Stacked avatars beyond this many would only add noise; the names say it all. */
const MAX_AVATARS = 3

const nameOf = (m: TaskManagerBrief) => m.name || '?'

/** One letter: at this size the overlap would cut a second one in half. */
const initialOf = (m: TaskManagerBrief) => initials(nameOf(m)).charAt(0)

const shown = computed(() => props.managers.slice(0, MAX_AVATARS))
const hiddenCount = computed(() => props.managers.length - shown.value.length)

const names = computed(() =>
  joinNames(
    props.managers.map((m) => nameOf(m)),
    locale.value,
  ),
)
</script>

<template>
  <span class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1" data-testid="task-managers">
    <span class="flex min-w-0 items-center gap-1.5">
      <span class="flex shrink-0 -space-x-1" aria-hidden="true">
        <Avatar v-for="m in shown" :key="m.user_id" class="size-5 ring-2 ring-background">
          <AvatarImage
            v-if="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })"
            :src="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })!"
          />
          <AvatarFallback class="text-[10px]">{{ initialOf(m) }}</AvatarFallback>
        </Avatar>
        <span
          v-if="hiddenCount > 0"
          class="bg-muted text-muted-foreground ring-background relative flex size-5 items-center justify-center rounded-full text-[9px] font-medium ring-2"
          data-testid="task-managers-more"
        >
          +{{ hiddenCount }}
        </span>
      </span>
      <span class="min-w-0">
        <span class="font-medium">{{ t('duties.tasks.managers.label') }}:</span>
        {{ names }}
      </span>
    </span>
    <Badge v-if="youAreInCharge" variant="secondary" data-testid="task-you-are-in-charge">
      <UserCheck aria-hidden="true" />
      {{ t('duties.tasks.managers.youAreInCharge') }}
    </Badge>
  </span>
</template>
