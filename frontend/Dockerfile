FROM cgr.dev/chainguard/node:latest-dev AS build-stage

USER root

WORKDIR /app

COPY package.json pnpm-lock.yaml ./

RUN corepack enable pnpm && pnpm install

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

ARG VITE_AUTH0_DOMAIN
ENV VITE_AUTH0_DOMAIN=${VITE_AUTH0_DOMAIN}

ARG VITE_AUTH0_CLIENT_ID
ENV VITE_AUTH0_CLIENT_ID=${VITE_AUTH0_CLIENT_ID}

ARG VITE_AUTH0_API_AUDIENCE
ENV VITE_AUTH0_API_AUDIENCE=${VITE_AUTH0_API_AUDIENCE}

ARG VITE_AUTH0_CALLBACK_URL
ENV VITE_AUTH0_CALLBACK_URL=${VITE_AUTH0_CALLBACK_URL}

ARG NODE_ENV=production
ENV NODE_ENV=${NODE_ENV}

RUN pnpm exec vite build

FROM cgr.dev/chainguard/nginx:latest AS production-stage

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["-g", "daemon off;"]
