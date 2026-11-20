FROM golang:1.24 AS builder
WORKDIR /src
RUN git clone https://github.com/minio/minio.git . && git checkout 9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
RUN CGO_ENABLED=0 go build -p 2 -trimpath -o /minio .
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /minio /usr/local/bin/minio
COPY --from=builder /src/LICENSE /usr/share/doc/minio/LICENSE
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server","/data","--console-address",":9001"]
