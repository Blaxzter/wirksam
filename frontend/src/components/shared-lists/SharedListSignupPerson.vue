<script setup lang="ts">
/**
 * Who signed up, in a sign-ups row: the name ("Guest (deleted)" once their
 * data is gone), "possibly a duplicate" when someone of the same name is on
 * the same shift, and the address and number when the viewer may see them.
 * Where the shift has no column of its own, it comes under the name.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'

import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListSignup } from '@/client/types.gen'

const props = defineProps<{
  signup: SharedListSignup
  withShift?: boolean
}>()

const { t } = useI18n()
const { personName, shiftText } = useSharedListText()

/**
 * The address split before its @, where a narrow column may wrap it, so
 * "p.neumann@example.org" never ends up as "p.neumann@example.or" over "g".
 */
const email = computed(() => {
  const address = props.signup.email
  if (!address) return null
  const at = address.lastIndexOf('@')
  return at > 0 ? { local: address.slice(0, at), domain: address.slice(at) } : null
})
const contact = computed(() => [props.signup.email, props.signup.phone].filter(Boolean).join(' · '))
</script>

<template>
  <div class="grid min-w-0 gap-0.5 whitespace-normal">
    <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span
        class="font-semibold"
        :class="props.signup.erased ? 'text-muted-foreground italic' : ''"
        data-testid="shared-list-signup-name"
      >
        {{ personName(props.signup.name, true) }}
      </span>
      <Badge
        v-if="props.signup.possible_duplicate"
        variant="warning"
        class="rounded-full"
        data-testid="shared-list-signup-duplicate"
      >
        {{ t('sharedLists.guest.possibleDuplicate') }}
      </Badge>
    </p>
    <p v-if="props.withShift" class="text-[12.5px] text-muted-foreground">
      {{ props.signup.task_name }} ·
      {{ shiftText(props.signup.shift_date, props.signup.start_time, props.signup.end_time) }}
    </p>
    <p
      v-if="contact"
      class="text-[12.5px] wrap-anywhere text-muted-foreground"
      data-testid="shared-list-signup-contact"
    >
      <template v-if="email">{{ email.local }}<wbr />{{ email.domain }}</template>
      <template v-else-if="props.signup.email">{{ props.signup.email }}</template>
      <template v-if="props.signup.email && props.signup.phone"> · </template>
      <template v-if="props.signup.phone">{{ props.signup.phone }}</template>
    </p>
  </div>
</template>
