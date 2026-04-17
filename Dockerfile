
FROM node:18 AS frontend-build

WORKDIR /app
COPY frontend/package.json .
COPY frontend/vite.config.js .
RUN npm install

COPY frontend/index.html .
COPY frontend/src ./src
RUN npm run build

FROM nginx:alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/dist /usr/share/nginx/html
