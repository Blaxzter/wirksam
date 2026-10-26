<script setup lang="ts">
import { computed, ref } from 'vue'

import { Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxViewport,
} from '@/components/ui/combobox'

import type { EventMemberRead } from '@/client/types.gen'
import { initials } from '@/lib/format'

/**
 * Search the event's people by name or email and pick one.
 *
 * Picking is the action: the parent adds the person straight away, so there
 * is no separate "Add" button and the field clears for the next name. People
 * in `unavailable` are listed but cannot be picked, with the reason beside
 * them, so "why is Marco not in the list?" never comes up.
 */
const props = withDefaults(
  defineProps<{
    members: EventMemberRead[]
    /** user id → why they cannot be picked (e.g. "Already in the team"). */
    unavailable?: Record<string, string>
    label: string
    placeholder?: string
    inputId?: string
    disabled?: boolean
    /** Shown when nobody matches the search. */
    emptyText?: string
    /** Beside the highlighted row: what Enter does ("Enter to add"). */
    actionHint?: string
    /** Prefix of the test ids: `<testid>`, `<testid>-list`, `<testid>-option-<id>`. */
    testid?: string
  }>(),
  {
    unavailable: undefined,
    placeholder: undefined,
    inputId: undefined,
    emptyText: undefined,
    actionHint: undefined,
    testid: 'member-picker',
  },
)

const emit = defineEmits<{ pick: [member: EventMemberRead] }>()

const { t } = useI18n()

const search = ref('')
const open = ref(false)

/** Shown at most; typing narrows it down. A huge event stays responsive. */
const LIMIT = 50

const matches = computed(() => {
  const q = search.value.trim().toLocaleLowerCase()
  const all = props.members.filter(
    (m) =>
      !q ||
      (m.name ?? '').toLocaleLowerCase().includes(q) ||
      (m.email ?? '').toLocaleLowerCase().includes(q),
  )
  // Pickable people first, so Enter on the first row adds someone.
  return [...all]
    .sort(
      (a, b) => Number(!!props.unavailable?.[a.user_id]) - Number(!!props.unavailable?.[b.user_id]),
    )
    .slice(0, LIMIT)
})

function nameOf(member: EventMemberRead): string {
  return member.name || member.email || '?'
}

function onPick(value: unknown) {
  const member = props.members.find((m) => m.user_id === value)
  if (!member || props.unavailable?.[member.user_id]) return
  emit('pick', member)
  search.value = ''
  open.value = false
}
</script>

<template>
  <div class="space-y-1.5">
    <label :for="inputId" class="text-sm font-medium">{{ label }}</label>
    <Combobox
      v-model:open="open"
      :model-value="null"
      ignore-filter
      open-on-focus
      :disabled="disabled"
      @update:model-value="onPick"
    >
      <ComboboxAnchor
        class="border-input focus-within:border-ring focus-within:ring-ring/50 flex w-full items-center rounded-md border bg-transparent shadow-xs focus-within:ring-[3px] [&_[data-slot=command-input-wrapper]]:w-full [&_[data-slot=command-input-wrapper]]:border-b-0"
      >
        <!-- The shadcn input brings its own search icon and bottom rule (it is
             built for a command palette); inside a bordered field we drop the
             rule. -->
        <ComboboxInput
          :id="inputId"
          v-model="search"
          class="h-9"
          :placeholder="placeholder"
          :data-testid="testid"
        />
      </ComboboxAnchor>
      <ComboboxList
        align="start"
        class="w-(--reka-combobox-trigger-width) min-w-64"
        :data-testid="`${testid}-list`"
      >
        <ComboboxViewport class="p-1">
          <ComboboxEmpty class="text-muted-foreground px-2 py-4">
            <Search class="mx-auto mb-1 size-4" />
            {{ emptyText ?? t('common.memberPicker.noMatch') }}
          </ComboboxEmpty>
          <ComboboxItem
            v-for="member in matches"
            :key="member.user_id"
            :value="member.user_id"
            :text-value="nameOf(member)"
            :disabled="!!unavailable?.[member.user_id]"
            class="group gap-3"
            :data-testid="`${testid}-option-${member.user_id}`"
          >
            <Avatar class="size-7">
              <AvatarImage
                v-if="avatarUrlFor({ id: member.user_id, avatar_etag: member.avatar_etag })"
                :src="avatarUrlFor({ id: member.user_id, avatar_etag: member.avatar_etag })!"
              />
              <AvatarFallback class="text-[10px]">{{ initials(nameOf(member)) }}</AvatarFallback>
            </Avatar>
            <span class="min-w-0 flex-1 truncate">
              <span class="font-medium">{{ nameOf(member) }}</span>
              <span v-if="member.name && member.email" class="text-muted-foreground text-xs">
                · {{ member.email }}
              </span>
            </span>
            <span
              v-if="unavailable?.[member.user_id]"
              class="text-muted-foreground shrink-0 text-xs"
            >
              {{ unavailable[member.user_id] }}
            </span>
            <span
              v-else
              class="text-muted-foreground hidden shrink-0 text-xs group-data-[highlighted]:sm:inline"
            >
              {{ actionHint ?? t('common.memberPicker.enterToPick') }}
            </span>
          </ComboboxItem>
        </ComboboxViewport>
      </ComboboxList>
    </Combobox>
  </div>
</template>
