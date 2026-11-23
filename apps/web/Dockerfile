FROM node:20-alpine AS dependencies

ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci \
    --registry="$NPM_REGISTRY" \
    --fetch-retries=4 \
    --fetch-retry-mintimeout=5000 \
    --fetch-retry-maxtimeout=30000 \
    --no-audit \
    --no-fund

FROM dependencies AS test
COPY . .
CMD ["sh", "-c", "npm run typecheck && npm run build"]

FROM dependencies AS build
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
