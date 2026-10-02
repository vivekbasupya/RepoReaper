FROM node:22.20.0-slim@sha256:b21fe589dfbe5cc39365d0544b9be3f1f33f55f3c86c87a76ff65a02f8f5848e AS build
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate
WORKDIR /app
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
COPY apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
RUN pnpm build
FROM nginx:1.28.0-alpine@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284
COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/containers/nginx.conf /etc/nginx/conf.d/default.conf
