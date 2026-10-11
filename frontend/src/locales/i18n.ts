import { watch } from 'vue'

import { createI18n } from 'vue-i18n'

import { installZodI18n } from '@/lib/zod-i18n'

// Define types for the module structure
interface TranslationModule {
  default?: Record<string, unknown>
  [key: string]: unknown
}

interface ModuleMap {
  [path: string]: TranslationModule
}

interface Messages {
  [filename: string]: Record<string, unknown>
}

// Dynamically import all translation files
const enModules = import.meta.glob('@/locales/en/*.json', { eager: true }) as ModuleMap
const deModules = import.meta.glob('@/locales/de/*.json', { eager: true }) as ModuleMap

// Helper function to create messages object from modules
function createMessagesFromModules(modules: ModuleMap): Messages {
  const messages: Messages = {}

  Object.entries(modules).forEach(([path, module]) => {
    // Extract filename without extension from the path
    const filename = path.split('/').pop()?.replace('.json', '')

    if (filename) {
      messages[filename] = module.default || module
    }
  })

  return messages
}

// Create the complete translation objects
const enMessages: Messages = createMessagesFromModules(enModules)
const deMessages: Messages = createMessagesFromModules(deModules)

const supportedLocales = ['en', 'de']

/**
 * The visitor's own choice: what they picked before, else the browser's
 * language. A public page under a locale prefix (`/de/…`) overrides this while
 * it is open, see `lib/page-head.ts`, which comes back here on the way out.
 *
 * Outside a browser, which is where the build-time prerender runs, there is no
 * choice to read and the prerender sets the locale itself.
 */
export function detectLocale(): string {
  if (typeof window === 'undefined') return 'en'
  const stored = localStorage.getItem('locale')
  if (stored) return stored
  const browserLang = navigator.language.split('-')[0]
  return supportedLocales.includes(browserLang) ? browserLang : 'en'
}

/** The locale prefix of the URL the app was opened on, if it has one. */
function urlLocale(): string | null {
  if (typeof window === 'undefined') return null
  const prefix = window.location.pathname.split('/')[1]
  return supportedLocales.includes(prefix) ? prefix : null
}

const i18n = createI18n({
  legacy: false,
  // Read once here so the very first render of `/de/…` is already German; the
  // router keeps it in step after that.
  locale: urlLocale() ?? detectLocale(),
  fallbackLocale: 'en',
  messages: {
    en: enMessages,
    de: deMessages,
  },
})

/**
 * Keep `<html lang>` in step with the active locale.
 *
 * `index.html` ships `lang="en"` so the first paint is never unlabelled, but the
 * locale is resolved at runtime from localStorage / navigator.language and can
 * be changed later from LanguageSwitch.vue or from the user's stored
 * `preferred_language` in stores/auth.ts. Doing it here rather than at each of
 * those call sites means a future third caller cannot forget.
 *
 * Without this, axe reports a serious `html-has-lang` violation and screen
 * readers announce German copy with an English voice (and vice versa).
 */
watch(
  i18n.global.locale,
  (locale) => {
    if (typeof document !== 'undefined') document.documentElement.lang = locale
  },
  { immediate: true },
)

/**
 * Point Zod's global error map at our copy.
 *
 * Here rather than in `main.ts` so that everything holding this module — the
 * app, and every Vitest spec that imports it — gets translated validation
 * messages with no second wiring step to forget. See `lib/zod-i18n.ts` for why
 * the generated schemas need no rebuild.
 */
installZodI18n((key, named) => (named ? i18n.global.t(key, named) : i18n.global.t(key)))

export default i18n
