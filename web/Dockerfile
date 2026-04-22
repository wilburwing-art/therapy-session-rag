# syntax=docker/dockerfile:1.7

# ---------- deps ----------
# Install production + dev deps needed to run `next build`.
FROM node:22-alpine AS deps

WORKDIR /app

# libc6-compat is the standard shim Next.js recommends on Alpine.
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---------- builder ----------
FROM node:22-alpine AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# next.config.ts must set `output: "standalone"` for this to produce
# .next/standalone + .next/static. Fails the build early if misconfigured.
RUN npm run build \
 && test -f .next/standalone/server.js

# ---------- runner ----------
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standard Next.js non-root user convention.
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 --ingroup nodejs nextjs

# Static assets + public/ must be copied alongside the standalone server.
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --quiet --spider "http://127.0.0.1:${PORT:-3000}/" || exit 1

CMD ["node", "server.js"]
