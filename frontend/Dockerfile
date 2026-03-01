FROM nginx:alpine

ARG DASHBOARD_USER=admin
ARG DASHBOARD_PASSWORD=changeme

RUN apk add --no-cache apache2-utils && \
    htpasswd -cb /etc/nginx/.htpasswd "$DASHBOARD_USER" "$DASHBOARD_PASSWORD"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY static/ /usr/share/nginx/html/
