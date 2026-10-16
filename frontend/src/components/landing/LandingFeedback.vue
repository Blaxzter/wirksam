<script setup lang="ts">
import { BugIcon, LightbulbIcon } from '@lucide/vue'
import { siGithub } from 'simple-icons'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import SimpleIcon from '@/components/utils/SimpleIcon.vue'

import { REPO_URL, feedbackMailto, newIssueUrl } from '@/lib/project-links'

import LandingSection from './LandingSection.vue'
import SectionHeading from './SectionHeading.vue'

const { t } = useI18n()
</script>

<template>
  <LandingSection id="feedback">
    <SectionHeading
      :eyebrow="t('preauth.landing.feedback.eyebrow')"
      :title="t('preauth.landing.feedback.title')"
      :lede="t('preauth.landing.feedback.lede')"
    />

    <div class="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
      <Button as-child size="lg" class="w-full gap-2 sm:w-auto">
        <a
          data-testid="btn-feedback-feature"
          :href="newIssueUrl('feature_request.yml')"
          target="_blank"
          rel="noopener"
        >
          <LightbulbIcon class="size-4" />
          {{ t('preauth.landing.feedback.featureButton') }}
        </a>
      </Button>
      <Button as-child size="lg" variant="outline" class="w-full gap-2 sm:w-auto">
        <a
          data-testid="btn-feedback-bug"
          :href="newIssueUrl('bug_report.yml')"
          target="_blank"
          rel="noopener"
        >
          <BugIcon class="size-4" />
          {{ t('preauth.landing.feedback.bugButton') }}
        </a>
      </Button>
      <Button as-child size="lg" variant="ghost" class="w-full gap-2 sm:w-auto">
        <a data-testid="btn-feedback-github" :href="REPO_URL" target="_blank" rel="noopener">
          <SimpleIcon :icon-data="siGithub" class-name="size-4" />
          {{ t('preauth.landing.feedback.githubButton') }}
        </a>
      </Button>
    </div>

    <p class="mt-4 text-center text-xs text-muted-foreground">
      {{ t('preauth.landing.feedback.accountHint') }}
      <a
        data-testid="link-feedback-email"
        :href="feedbackMailto(t('preauth.landing.feedback.emailSubject'))"
        class="font-medium text-foreground underline underline-offset-4 hover:text-primary"
      >
        {{ t('preauth.landing.feedback.emailLink') }}
      </a>
    </p>
  </LandingSection>
</template>
