FROM nginx:alpine

RUN apk add --no-cache apache2-utils

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY static/ /usr/share/nginx/html/
RUN mv /usr/share/nginx/html/index.html /usr/share/nginx/html/index.html.template

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
