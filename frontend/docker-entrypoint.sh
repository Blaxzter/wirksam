#!/bin/sh
# Generate runtime config from environment variables before starting nginx.
cat > /usr/share/nginx/html/config.js <<EOF
window.__APP_CONFIG__ = {
  LEGAL_NAME: '${LEGAL_NAME:-}',
  LEGAL_ADDRESS: '${LEGAL_ADDRESS:-}',
  LEGAL_CITY: '${LEGAL_CITY:-}',
  LEGAL_EMAIL: '${LEGAL_EMAIL:-}',
  LEGAL_PHONE: '${LEGAL_PHONE:-}',
  TURNSTILE_SITE_KEY: '${TURNSTILE_SITE_KEY:-}',
  // Defaults to on, like the backend setting it mirrors: an unset variable
  // must not silently take the demo away. Only the literal 'false' hides it.
  SANDBOX_ENABLED: '${SANDBOX_ENABLED:-true}',
  // Whether / shows the landing page or leads straight to sign-in. Read like
  // SANDBOX_ENABLED: only the literal 'false' switches it off.
  LANDING_ENABLED: '${LANDING_ENABLED:-true}',
};
EOF

HTML_DIR=/usr/share/nginx/html

# The public pages are prerendered once per combination of the runtime switches
# that change them (scripts/prerender.mjs, `TOGGLES`: same list, same order).
# Everything on is already in place; otherwise copy the matching set over it.
# A switch is off only for the literal 'false', ignoring case and spaces, the
# way isSwitchOn() in src/composables/useAppConfig.ts reads it.
is_off() {
  [ "$(printf '%s' "$1" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')" = "false" ]
}
OFF=""
if is_off "${SANDBOX_ENABLED:-true}"; then OFF="$OFF-sandbox"; fi
if is_off "${LANDING_ENABLED:-true}"; then OFF="$OFF-landing"; fi
if [ -n "$OFF" ]; then
  cp -R "$HTML_DIR/_prerender/off$OFF/." "$HTML_DIR/" \
    || echo "warning: no prerendered pages for off$OFF, serving the defaults" >&2
fi
rm -rf "$HTML_DIR/_prerender"

# The prerendered public pages, sitemap.xml, robots.txt and llms.txt are built
# with absolute URLs for the public instance (scripts/prerender.mjs). Point them
# at this deployment instead. No -maxdepth: the pages nest as deep as their
# routes (de/use-cases/<page>/index.html), and _prerender is already gone.
BUILT_SITE_URL='https://wirksam.app'
SITE_URL="${FRONTEND_HOST%/}"
if [ -n "$SITE_URL" ] && [ "$SITE_URL" != "$BUILT_SITE_URL" ]; then
  find "$HTML_DIR" -type f \( -name '*.html' -o -name '*.xml' -o -name '*.txt' \) \
    -exec sed -i "s#${BUILT_SITE_URL}#${SITE_URL}#g" {} +
fi

# A private deployment can ask every crawler to stay away. Only the literal
# 'false' does it, so an unset variable keeps the public pages findable.
if [ "${SEARCH_INDEXING:-true}" = "false" ]; then
  rm -f "$HTML_DIR/robots.txt" "$HTML_DIR/sitemap.xml" "$HTML_DIR/llms.txt"
  printf 'User-agent: *\nDisallow: /\n' > "$HTML_DIR/robots.txt"
fi

exec nginx -g 'daemon off;'
