FROM node:18-alpine AS build
WORKDIR /app

# Inject build tag and exact Git commit into the frontend build/runtime marker.
ARG REZZERV_VERSION
ARG REZZERV_COMMIT=unknown
ENV VITE_REZZERV_VERSION=${REZZERV_VERSION}
ENV VITE_REZZERV_COMMIT=${REZZERV_COMMIT}
COPY package.json .
RUN npm install
COPY . .
RUN node ./node_modules/vite/bin/vite.js build \
    && printf '{"version":"%s","commit":"%s"}\n' "$REZZERV_VERSION" "$REZZERV_COMMIT" > /app/dist/version.json

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
