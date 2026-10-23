# geo-observer (Rascunho inicial)
Trabalho desenvolvido na disciplina de Sistemas Distribuídos da faculdade.

## Ideia geral

O objetivo do projeto é construir um sistema distribuído capaz de processar imagens de satélite (arquivos `.tif`) para identificar objetos/padrões usando visão computacional e exibir os resultados em um mapa web conforme o processamento avança.

Como imagens de satélite costumam ser muito grandes e pesadas para processar de uma vez só em um único processo, a ideia central para aplicar os conceitos da disciplina é recortar a imagem original em blocos menores (*tiles*) e distribuir esses pedaços entre múltiplos nós de processamento (*workers*). Conforme cada *worker* termina seu pedaço, o front-end vai atualizando o mapa em tempo real.

## Fluxo básico até agora

1. **Interface Web:** O usuário seleciona uma área no mapa (ou envia um arquivo `.tif` de teste) para análise.
2. **API Backend:** Recebe a requisição, guarda o arquivo `.tif` bruto em um armazenamento separado (para não trafegar arquivos grandes pela rede/fila) e divide o trabalho em tarefas menores.
3. **Middleware (Fila de Mensagens):** Recebe apenas as referências (links/coordenadas de cada recorte) e distribui para os *workers* disponíveis.
4. **Workers de Processamento:** Cada instância puxa o pedaço correspondente da imagem, roda a predição do modelo e salva os polígonos encontrados no banco de dados.
5. **Retorno para o Usuário:** Um serviço de cache/notificação avisa a API à medida que os pedaços ficam prontos, atualizando a tela do usuário (provavelmente via WebSocket).

## Stack inicial

* **Backend / API:** Python (FastAPI)
* **Armazenamento de Arquivos:** MinIO (para salvar os `.tif` brutos fora do banco relacional)
* **Banco de Dados:** PostgreSQL com extensão PostGIS (para lidar com os metadados geográficos e polígonos gerados)
* **Cache / Estado:** Redis (para controle rápido do progresso das tarefas)
* **Ambiente:** Docker (ideal para simular serviços em paralelo)
* **Interface Web:** React ou algo parecido

## Pontos em aberto

Como ainda estou estruturando a base da arquitetura, existem algumas escolhas técnicas que estou avaliando se valem a pena para o escopo do trabalho:

1. **RabbitMQ vs. Redis puro no Middleware:** A ideia principal é usar o **RabbitMQ** para gerenciar a fila de tarefas e lidar com reenvio caso algum *worker* caia no meio do processamento. A dúvida é se o RabbitMQ adiciona muita complexidade de configuração junto com o Redis ou se é melhor manter os dois separados mesmo para deixar o papel do *broker* bem definido.
2. **Uso do ONNX nos Workers:** Para rodar vários containers de *worker* na mesma máquina de teste sem estourar a memória RAM, pensei em exportar o modelo de visão computacional para o formato **ONNX** (usando `onnxruntime`) em vez de subir o PyTorch completo em cada container. Ainda preciso testar se isso complica a etapa de pós-processamento das coordenadas geográficas.
3. **Integração com API do Google Earth / Autenticação:** No desenho inicial, pensei em buscar os arquivos `.tif` direto da API do Google Earth Engine e colocar login com conta Google. Porém, dependendo do tempo disponível, estou considerando deixar essa integração externa como opcional e focar primeiro no upload direto de arquivos `.tif` locais para priorizar os requisitos de sistemas distribuídos (concorrência, tolerância a falhas e comunicação entre os nós).

## Próximos Passos

- [ ] Fechar a definição final das ferramentas após validação da proposta.
- [ ] Montar o `docker-compose.yml` básico com o banco e a fila.
- [ ] Testar o recorte de uma imagem `.tif` pequena enviando tarefas simples para 2 *workers*.
