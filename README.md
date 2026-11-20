# Geo Observer

Plataforma web para enviar imagens GeoTIFF, desenhar áreas de interesse e executar inferência geográfica distribuída. A API planeja recortes; um publicador envia referências de tarefas pelo RabbitMQ; dois workers processam os recortes e gravam resultados no PostGIS. O mapa apresenta as classes previstas.

> **Demonstração publicada:** [Geo Observer](https://geo-observer.18.219.115.228.sslip.io) · [Documentação da API](https://geo-observer.18.219.115.228.sslip.io/api/docs)
>
> A instância está na AWS e usa um endereço provisório `sslip.io`, associado ao IP atual. Pode haver consumo de créditos/custos da conta. Imagens, contas e resultados locais não são migrados para a demonstração.

## O que o sistema faz

- Cadastro e login por senha, com opção de login Google na instância publicada.
- Upload, lista, prévia, localização, renomeação e exclusão protegida de GeoTIFF.
- Busca opcional de cenas Sentinel-2 pelo Google Earth Engine.
- Desenho de áreas de interesse no mapa e análises limitadas ao polígono.
- Planejamento de tarefas, processamento em dois workers e acompanhamento de progresso.
- Visualização e limpeza da camada de inferência no mapa.

## Arquitetura atual

O frontend é HTML, CSS e JavaScript servido por Nginx em um container próprio. Ele conversa com a API FastAPI por HTTP. O projeto não usa React, Redis ou WebSocket: o progresso é consultado periodicamente pela API, e o estado fica no PostgreSQL/PostGIS.

RabbitMQ distribui IDs de tarefas. A API registra tarefa e outbox na mesma transação; o publicador entrega mensagens persistentes com confirmação; workers separados recebem e confirmam após concluir a transação. MinIO guarda os arquivos e recortes. O Docker Compose descreve cada serviço em um container próprio; não é um único container com toda a stack. Em HTTPS, Caddy é acrescentado pelo arquivo Compose opcional.

O modelo ONNX incluído é um exemplo pré-treinado de cobertura do solo, não foi treinado neste trabalho e não é um detector de veículos ou de mudanças de desmatamento. Cenas Sentinel-2 têm 10 m/pixel e os resultados são exploratórios.

## Executar a stack completa localmente

Requisitos: Git, Docker Desktop com Compose e conexão à internet para baixar as imagens e construir o container MinIO.

```bash
git clone https://github.com/samuelicaro/geo-observer.git
cd geo-observer
cp .env.deploy.example .env.deploy
docker compose --env-file .env.deploy -f compose.deploy.yaml up -d --build
```

Antes de iniciar, abra `.env.deploy` e defina senhas fortes e diferentes para `POSTGRES_PASSWORD`, `MINIO_PASSWORD` e `RABBITMQ_PASSWORD`. O arquivo contém credenciais locais e não deve ser enviado ao Git.

Abra [http://localhost:8080](http://localhost:8080). O Compose inicia PostGIS, MinIO, RabbitMQ, API, frontend, inicializador do banco/bucket, publicador e dois workers. A primeira compilação do MinIO pode levar alguns minutos. Os serviços de infraestrutura não publicam portas no host; a interface encaminha `/api` para a API pela rede interna do Compose.

Verificar estado e logs:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml ps
docker compose --env-file .env.deploy -f compose.deploy.yaml logs -f api publicador worker1 worker2
```

Para parar mantendo os volumes de dados, execute `docker compose --env-file .env.deploy -f compose.deploy.yaml down`. **Não acrescente `-v`** se quiser manter banco, objetos e mensagens.

O login Google e o Earth Engine são opcionais em uma instalação local. Configure `GOOGLE_CLIENT_ID` e as credenciais do Earth Engine apenas se for usar esses recursos.

### HTTPS em uma máquina com domínio

Aponte um domínio seu para o IP público, libere TCP 80/443, configure `SITE_ADDRESS` com o nome DNS e `COOKIE_SECURE=true` em `.env.deploy`; então inicie também o Caddy:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml -f compose.https.yaml up -d --build
```

Caddy obtém e renova o certificado TLS quando o DNS e as portas estão configurados. A demonstração pública atual usa essa configuração HTTPS.

## Containers e Docker Compose

O projeto não é um único container. `compose.deploy.yaml` inicia containers separados para a interface, API, PostgreSQL/PostGIS, MinIO, RabbitMQ, publicador e dois workers. Cada parte pode ser iniciada e escalada separadamente. `compose.https.yaml` adiciona o Caddy para HTTPS quando há um domínio configurado.

## Estrutura principal

```text
api/            rotas FastAPI, autenticação, Earth Engine e acesso aos serviços
models/         todos os modelos ORM SQLAlchemy
worker/         publicador da outbox, consumidores, recorte e inferência ONNX
static/         frontend independente, mapa e recursos do navegador
modelos/        modelo ONNX, manifesto, licença e TIFF de demonstração
infra/          Nginx, Caddy e imagens de infraestrutura
compose.deploy.yaml  stack completa
compose.https.yaml   camada HTTPS opcional com Caddy
```

## Estado e limitações

A stack foi construída e executada em uma VM AWS; os artefatos locais mais recentes ainda precisam ser enviados ao GitHub para o repositório remoto refletir o trabalho. A autenticação Google está configurada no servidor, mas o fluxo de popup ainda precisa ser confirmado com uma entrada real pelo navegador.

Uma única VM é ponto único de falha e compartilha CPU/RAM entre os containers. O modelo não tem avaliação formal em imagens brasileiras; não use as previsões como decisão operacional. Earth Engine acessa a coleção Sentinel-2, não o Google Satellite/QuickMap de alta resolução. Consulte as limitações e os custos atuais do provedor antes de manter a VM ligada.
