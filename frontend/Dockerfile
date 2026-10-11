FROM cgr.dev/chainguard/node:latest-dev AS build-stage

USER root

WORKDIR /app

COPY package.json pnpm-lock.yaml ./

# Pin pnpm to package.json's `packageManager` so the lockfile is resolved by the
# same major that generated it.
RUN npm install -g \
    "pnpm@$(node -p "require('./package.json').packageManager.replace(/^pnpm@/, '').split('+')[0]")" \
    && pnpm install

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

ARG NODE_ENV=production
ENV NODE_ENV=${NODE_ENV}

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# `build-only` is `vite build` followed by the prerender of the public pages
# (scripts/prerender.mjs), which also writes sitemap.xml, robots.txt and llms.txt.
RUN pnpm build-only

FROM cgr.dev/chainguard/nginx:latest-dev AS production-stage

USER root
# Owned by nginx: docker-entrypoint.sh rewrites the prerendered pages in every
# subdirectory, not just the top-level config.js.
COPY --from=build-stage --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && chmod 777 /usr/share/nginx/html
USER nginx

EXPOSE 80

ENTRYPOINT ["/bin/sh", "/docker-entrypoint.sh"]
