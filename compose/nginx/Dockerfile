FROM nginx:1.27-alpine

# Which conf to bake in (prod by default; staging passes nginx.staging.conf).
ARG NGINX_CONF=nginx.conf

RUN rm /etc/nginx/conf.d/default.conf
COPY compose/nginx/${NGINX_CONF} /etc/nginx/conf.d/app.conf
