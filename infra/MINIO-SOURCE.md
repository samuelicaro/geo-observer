# MinIO compilado do código oficial

O download minio/minio no Docker Hub falhou na publicação; quay.io também recusou acesso. O Compose constrói o servidor via infra/minio.Dockerfile.

Fonte: https://github.com/minio/minio
Release: RELEASE.2025-10-15T17-29-55Z
Revisão fixa: 9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
Código correspondente: https://github.com/minio/minio/tree/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
Licença AGPL-3.0: copiada para /usr/share/doc/minio/LICENSE na imagem. Não há alterações no código do MinIO. O build usa Go 1.24, CGO desabilitado e paralelismo de compilação limitado a dois processos. Não expõe portas S3/console ao público; acesso somente pela rede dos containers.
