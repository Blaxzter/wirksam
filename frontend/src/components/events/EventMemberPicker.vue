<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Search, Send } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  VisuallyHidden,
} from 'reka-ui'
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
import { RESPONSIVE_DIALOG_MOBILE_QUERY } from '@/components/ui/responsive-dialog'

import type { EventMemberRead } from '@/client/types.gen'
import { addressNameParts, looksLikeEmail } from '@/lib/email'
import { initials } from '@/lib/format'

/**
 * Search the event's people by name or email and pick one.
 *
 * Picking is the action: the parent adds the person straight away, so there
 * is no separate "Add" button and the field clears for the next name. People
 * in `unavailable` are listed but cannot be picked, with the reason beside
 * them, so "why is Marco not in the list?" never comes up.
 *
 * With `allowEmail`, an address that belongs to no member is offered as
 * "Invite … " (emitted as `invite`); a member's address simply finds the
 * member. Members whose name looks like the address are listed under it, so
 * an organiser notices that Jonas is already in under another address.
 *
 * With `phoneSheet`, a phone gets a full-screen picker instead of a dropdown:
 * the field opens it, and the list fills the screen above the keyboard rather
 * than squeezing into a popup over a bottom sheet. With `hideField` as well,
 * the field is left out and the parent opens the sheet from a button of its
 * own through `v-model:sheet-open` (the redeem page's "Pick a person").
 *
 * The `trailing` slot puts something at the end of each row, in the sheet and
 * in the dropdown alike (how many vouchers someone has, when redeeming).
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
    /** Offer to invite a typed address that belongs to no member. */
    allowEmail?: boolean
    /** On phones, pick in a full-screen sheet instead of a dropdown. */
    phoneSheet?: boolean
    /** The full-screen sheet's name for screen readers; defaults to `label`. */
    sheetTitle?: string
    /** The line under the search field in the full-screen sheet. */
    sheetContext?: string
    /**
     * With `phoneSheet`, on a phone: no field and no label, only the sheet,
     * which the parent opens through `v-model:sheet-open`. Elsewhere the
     * picker renders nothing, so the parent shows its own picker there.
     */
    hideField?: boolean
  }>(),
  {
    unavailable: undefined,
    placeholder: undefined,
    inputId: undefined,
    emptyText: undefined,
    actionHint: undefined,
    testid: 'member-picker',
    sheetTitle: undefined,
    sheetContext: undefined,
  },
)

const emit = defineEmits<{ pick: [member: EventMemberRead]; invite: [email: string] }>()

defineSlots<{
  /** At the end of a member's row, in the sheet and in the dropdown. */
  trailing?: (props: { member: EventMemberRead }) => unknown
}>()

/** The full-screen sheet is open. */
const sheetOpen = defineModel<boolean>('sheetOpen', { default: false })

const { t } = useI18n()

const search = ref('')
const open = ref(false)

/** Shown at most; typing narrows it down. A huge event stays responsive. */
const LIMIT = 50

/**
 * The combobox value of the "Invite …" row is this prefix and the address;
 * member rows carry user ids. The address travels in the value because reka
 * clears the search (and with it `inviteEmail`) before it reports the pick.
 */
const INVITE = 'invite:'

const isPhone = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)
const usesSheet = computed(() => props.phoneSheet && isPhone.value)

/** The typed address when it can be invited: no member has it. */
const inviteEmail = computed(() => {
  if (!props.allowEmail) return null
  const q = search.value.trim()
  if (!looksLikeEmail(q)) return null
  const lower = q.toLocaleLowerCase()
  if (props.members.some((m) => (m.email ?? '').toLocaleLowerCase() === lower)) return null
  return q
})

/** Before the `@`, where a name usually is. */
const localPart = (email: string | null | undefined) =>
  (email ?? '').toLocaleLowerCase().split('@')[0] ?? ''

const matches = computed(() => {
  const q = search.value.trim().toLocaleLowerCase()
  // An address nobody has would match nobody; list who may be the same
  // person instead ("jonas.weber@…" → Jonas Albrecht).
  const parts = inviteEmail.value ? addressNameParts(inviteEmail.value) : []
  const all = props.members.filter((m) => {
    const name = (m.name ?? '').toLocaleLowerCase()
    if (!q || name.includes(q) || (m.email ?? '').toLocaleLowerCase().includes(q)) return true
    return parts.some((part) => name.includes(part) || localPart(m.email).includes(part))
  })
  // Pickable people first, so Enter on the first row adds someone.
  return [...all]
    .sort(
      (a, b) => Number(!!props.unavailable?.[a.user_id]) - Number(!!props.unavailable?.[b.user_id]),
    )
    .slice(0, LIMIT)
})

/** The full-screen list's heading: everyone, or who looks like the address. */
const listTitle = computed(() => {
  if (inviteEmail.value) return matches.value.length ? t('common.memberPicker.similar') : null
  return search.value.trim() ? null : t('common.memberPicker.allMembers')
})

function nameOf(member: EventMemberRead): string {
  return member.name || member.email || '?'
}

function reset() {
  search.value = ''
  open.value = false
  sheetOpen.value = false
}

function pickMember(member: EventMemberRead) {
  if (props.unavailable?.[member.user_id]) return
  emit('pick', member)
  reset()
}

function invite(email: string | null = inviteEmail.value) {
  if (!email) return
  emit('invite', email)
  reset()
}

function onPick(value: unknown) {
  if (props.allowEmail && typeof value === 'string' && value.startsWith(INVITE)) {
    invite(value.slice(INVITE.length))
    return
  }
  const member = props.members.find((m) => m.user_id === value)
  if (member) pickMember(member)
}

/**
 * Enter in the full-screen search: what the first row offers. Only once
 * something is typed: the sheet highlights no row, so "Go" on the whole
 * roster would quietly pick whoever happens to be first.
 */
function pickFirst() {
  if (!search.value.trim()) return
  if (inviteEmail.value) {
    invite()
    return
  }
  const first = matches.value.find((m) => !props.unavailable?.[m.user_id])
  if (first) pickMember(first)
}

// A search left behind in a closed sheet would greet the next opening.
watch(sheetOpen, (isOpen) => {
  if (!isOpen) search.value = ''
})
</script>

<template>
  <div class="space-y-1.5">
    <label v-if="!hideField" :for="inputId" class="text-sm font-medium">{{ label }}</label>

    <!-- Phone: a field that opens the full-screen picker -->
    <template v-if="usesSheet">
      <button
        v-if="!hideField"
        :id="inputId"
        type="button"
        class="border-input focus-visible:border-ring focus-visible:ring-ring/50 text-muted-foreground flex h-11 w-full items-center gap-2 rounded-md border bg-transparent px-3 text-left text-base shadow-xs outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="disabled"
        aria-haspopup="dialog"
        :data-testid="testid"
        @click="sheetOpen = true"
      >
        <Search class="size-4 shrink-0 opacity-60" aria-hidden="true" />
        <span class="truncate">{{ placeholder ?? label }}</span>
      </button>

      <DialogRoot v-model:open="sheetOpen">
        <DialogPortal>
          <!-- Above the bottom sheet it is opened from (z-50). -->
          <DialogContent
            class="bg-background text-foreground fixed inset-0 z-60 flex flex-col focus:outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-bottom-4"
            :data-testid="`${testid}-sheet`"
          >
            <VisuallyHidden>
              <DialogTitle>{{ sheetTitle ?? label }}</DialogTitle>
              <DialogDescription v-if="sheetContext">{{ sheetContext }}</DialogDescription>
            </VisuallyHidden>

            <header class="space-y-2 border-b px-4 pt-3.5 pb-3">
              <div class="flex items-center gap-2">
                <label
                  class="border-ring focus-within:ring-ring/40 flex min-h-12 min-w-0 flex-1 items-center gap-2 rounded-xl border-2 px-3 focus-within:ring-[3px]"
                >
                  <Search class="text-muted-foreground size-4.5 shrink-0" aria-hidden="true" />
                  <span class="sr-only">{{ label }}</span>
                  <input
                    v-model="search"
                    type="search"
                    autocomplete="off"
                    autocapitalize="off"
                    spellcheck="false"
                    enterkeyhint="go"
                    class="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground"
                    :placeholder="placeholder"
                    :data-testid="`${testid}-sheet-input`"
                    @keydown.enter.prevent="pickFirst"
                  />
                </label>
                <DialogClose
                  class="text-primary min-h-12 shrink-0 rounded-md px-1.5 text-base font-semibold focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {{ t('common.actions.cancel') }}
                </DialogClose>
              </div>
              <p v-if="sheetContext" class="text-muted-foreground text-sm">{{ sheetContext }}</p>
            </header>

            <div
              class="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)]"
            >
              <div v-if="inviteEmail" class="px-3 pt-3 pb-1">
                <button
                  type="button"
                  class="border-primary/30 bg-primary/8 hover:bg-primary/12 focus-visible:ring-ring flex min-h-16 w-full items-center gap-3 rounded-2xl border px-3 py-2.5 text-left focus-visible:ring-2 focus-visible:outline-none"
                  :data-testid="`${testid}-invite`"
                  @click="invite()"
                >
                  <span
                    class="bg-primary text-primary-foreground flex size-10.5 shrink-0 items-center justify-center rounded-full"
                    aria-hidden="true"
                  >
                    <Send class="size-4.5" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="block text-base font-bold">
                      {{ t('duties.tasks.managers.inviteByEmail') }}
                    </span>
                    <span class="block truncate text-sm">{{ inviteEmail }}</span>
                    <span class="text-muted-foreground block text-[13px]">
                      {{ t('duties.tasks.managers.inviteByEmailHint') }}
                    </span>
                  </span>
                </button>
              </div>

              <h2
                v-if="listTitle"
                class="text-muted-foreground px-5 pt-3.5 pb-1.5 text-xs font-bold tracking-wide uppercase"
              >
                {{ listTitle }}
              </h2>
              <ul class="px-2 pb-4" :data-testid="`${testid}-list`">
                <li v-for="member in matches" :key="member.user_id">
                  <button
                    type="button"
                    class="hover:bg-accent focus-visible:ring-ring flex min-h-15 w-full items-center gap-3 rounded-xl px-3 py-2 text-left focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50"
                    :disabled="!!unavailable?.[member.user_id]"
                    :data-testid="`${testid}-option-${member.user_id}`"
                    @click="pickMember(member)"
                  >
                    <Avatar class="size-10 shrink-0">
                      <AvatarImage
                        v-if="avatarUrlFor({ id: member.user_id, avatar_etag: member.avatar_etag })"
                        :src="
                          avatarUrlFor({ id: member.user_id, avatar_etag: member.avatar_etag })!
                        "
                      />
                      <AvatarFallback class="text-sm font-bold">
                        {{ initials(nameOf(member)) }}
                      </AvatarFallback>
                    </Avatar>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate text-base font-semibold">{{
                        nameOf(member)
                      }}</span>
                      <span class="text-muted-foreground block truncate text-[13px]">
                        {{ unavailable?.[member.user_id] ?? (member.name ? member.email : '') }}
                      </span>
                    </span>
                    <slot name="trailing" :member="member" />
                  </button>
                </li>
              </ul>
              <p
                v-if="!inviteEmail && matches.length === 0"
                class="text-muted-foreground px-5 py-6 text-center text-sm"
              >
                {{ emptyText ?? t('common.memberPicker.noMatch') }}
              </p>
            </div>
          </DialogContent>
        </DialogPortal>
      </DialogRoot>
    </template>

    <!-- Wider screens: a search field with a dropdown -->
    <Combobox
      v-else-if="!hideField"
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
            v-if="inviteEmail"
            :value="INVITE + inviteEmail"
            :text-value="inviteEmail"
            class="group gap-3 py-2"
            :data-testid="`${testid}-invite`"
          >
            <span
              class="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-full"
              aria-hidden="true"
            >
              <Send class="text-primary-foreground size-3.5" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate font-semibold">
                {{ t('duties.tasks.managers.inviteOption', { email: inviteEmail }) }}
              </span>
              <span class="text-muted-foreground block text-xs">
                {{ t('duties.tasks.managers.inviteOptionHint') }}
              </span>
            </span>
            <kbd
              class="text-muted-foreground hidden shrink-0 rounded border px-1.5 py-0.5 font-sans text-[11px] group-data-[highlighted]:sm:inline"
            >
              {{ t('common.memberPicker.enterKey') }}
            </kbd>
          </ComboboxItem>
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
              <span v-if="inviteEmail" class="text-muted-foreground text-xs">
                · {{ t('duties.tasks.managers.inEvent') }}
              </span>
            </span>
            <slot name="trailing" :member="member" />
            <span
              v-if="unavailable?.[member.user_id]"
              class="text-muted-foreground shrink-0 text-xs"
            >
              {{ unavailable[member.user_id] }}
            </span>
            <span
              v-else-if="!inviteEmail"
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
