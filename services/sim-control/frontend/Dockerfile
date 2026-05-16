FROM node:20-alpine AS base
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=base /app/next.config.js ./
COPY --from=base /app/.next/standalone ./
COPY --from=base /app/.next/static ./.next/static
EXPOSE 3001
ENV PORT=3001
CMD ["node", "server.js"]
