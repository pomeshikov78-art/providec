# АИС «Техноконтур» — фронтенд (единый HTML-клиент + nginx reverse-proxy)
FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY ais_providets.html /usr/share/nginx/html/index.html

EXPOSE 80 443
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/healthz || exit 1
