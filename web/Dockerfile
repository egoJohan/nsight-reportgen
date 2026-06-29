# nSight web UI: build the Vite SPA, serve it via nginx, and reverse-proxy the
# API to the backend (same origin -> no CORS, one published port).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Relative API base: the SPA calls /cases, /materials, /chart-types on its own
# origin; nginx proxies those to the backend.
ENV VITE_API_BASE=""
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
