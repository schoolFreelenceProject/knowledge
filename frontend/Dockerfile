FROM node:22-alpine AS build

WORKDIR /app
ARG VITE_API_TIMEOUT_MS=1800000
ENV VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html postcss.config.js tailwind.config.ts tsconfig.json tsconfig.node.json vite.config.ts ./
COPY src ./src
RUN npm run build


FROM nginx:1.27-alpine

ENV NGINX_CLIENT_MAX_BODY_SIZE=256m \
    NGINX_PROXY_READ_TIMEOUT=1800s \
    NGINX_PROXY_SEND_TIMEOUT=1800s

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
