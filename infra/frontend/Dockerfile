# syntax=docker/dockerfile:1.7
# Smart Campus Digital Twin — Three.js / Next.js frontend
#
# Build context is the repo root so git submodule files are available.
# The Next.js app lives at frontend/frontend/ inside the submodule.
#
# Build args (baked into the static bundle at build time):
#   NEXT_PUBLIC_API_URL  — Base URL of the FastAPI backend (default: /api proxy)

# ---------------------------------------------------------------------------
# Stage 1 — install npm dependencies (cached layer)
# ---------------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app
COPY frontend/frontend/package.json frontend/frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install

# ---------------------------------------------------------------------------
# Stage 2 — build the Next.js application
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/frontend/ ./

ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_KEYCLOAK_URL=/auth
ARG NEXT_PUBLIC_KEYCLOAK_REALM=campus
ARG NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=campus-frontend
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_KEYCLOAK_URL=${NEXT_PUBLIC_KEYCLOAK_URL}
ENV NEXT_PUBLIC_KEYCLOAK_REALM=${NEXT_PUBLIC_KEYCLOAK_REALM}
ENV NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=${NEXT_PUBLIC_KEYCLOAK_CLIENT_ID}
ENV NEXT_TELEMETRY_DISABLED=1

RUN rm -rf .next
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 3 — production runner (minimal image, no node_modules bloat)
# ---------------------------------------------------------------------------
FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# Copy only the standalone output + static assets — smallest possible footprint
COPY --from=builder --chown=nextjs:nodejs /app/public          ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next           ./.next
COPY --from=builder --chown=nextjs:nodejs /app/node_modules    ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/package.json    ./package.json

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["npm", "start"]
