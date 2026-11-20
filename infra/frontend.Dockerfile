FROM nginx:1.28-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY static /usr/share/nginx/html/static
COPY static/index.html /usr/share/nginx/html/index.html
COPY static/entrar.html /usr/share/nginx/html/entrar.html
COPY modelos/amostra-demonstracao.tif /usr/share/nginx/html/amostra.tif
