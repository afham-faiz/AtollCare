# F-M7.3 Web image: build with bun, run the Next.js standalone server.
FROM oven/bun:1.3 AS build
WORKDIR /web
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
ARG NEXT_PUBLIC_ENGINE_URL=/api
ARG ENGINE_INTERNAL_URL=http://engine:8000
ENV NEXT_PUBLIC_ENGINE_URL=$NEXT_PUBLIC_ENGINE_URL ENGINE_INTERNAL_URL=$ENGINE_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
RUN bun run build

FROM node:22-slim
WORKDIR /web
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
COPY --from=build /web/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
