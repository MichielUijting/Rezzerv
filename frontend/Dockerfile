FROM node:18-alpine AS build
WORKDIR /app

# Inject build tag into the Vite build (so the UI can show the correct version).
ARG REZZERV_VERSION
ENV VITE_REZZERV_VERSION=${REZZERV_VERSION}
COPY package.json .
RUN npm install
COPY . .
RUN node ./node_modules/vite/bin/vite.js build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
