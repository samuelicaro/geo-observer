const arquivo = document.getElementById('arquivo_tif');

const enviar = document.getElementById('enviar_tif');
enviar.addEventListener('click', async () => {
    const file = arquivo.files[0];
    if (!file) {
        alert('Selecione um arquivo antes de enviar.');
        return;
    }
    if (!/\.tiff?$/i.test(file.name) || file.size === 0) {
        alert('Selecione um arquivo .tif ou .tiff válido e não vazio.');
        arquivo.value = '';
        return;
    }
    const limite = Number(document.querySelector('[name="MAX_FILE_SIZE"]').value);
    if (file.size > limite) {
        alert('O arquivo excede o limite de 300 MB.');
        arquivo.value = '';
        return;
    }
    arquivo.disabled = true;
    enviar.disabled = true;
    enviar.textContent = 'Enviando…';
    try {
        const response = await fetch('/imagens/?nome=' + encodeURIComponent(file.name), {
            method: 'POST',
            headers: {'Content-Type': 'image/tiff'},
            body: file
        });
        const data = await response.json().catch(() => null);
        if (!response.ok) {
            const detail = typeof data?.detail === 'string' ? data.detail : null;
            alert(detail || `Não foi possível enviar o arquivo (HTTP ${response.status}).`);
            return;
        }
        alert(`Imagem enviada com sucesso! ID: ${data.id}`);
        await carregarImagens(true);
    } catch {
        alert('Falha de conexão. Confira os registros na API antes de reenviar: o arquivo pode ter sido salvo.');
    } finally {
        arquivo.disabled = false;
        enviar.disabled = false;
        enviar.textContent = 'Enviar arquivo';
        arquivo.value = '';
    }
});

const listaImagens = document.getElementById('lista_imagens');
const statusImagens = document.getElementById('status_imagens');
const atualizarImagens = document.getElementById('atualizar_imagens');
const maisImagens = document.getElementById('mais_imagens');
let offsetImagens = 0;
let requisicaoImagens;

async function carregarImagens(reiniciar = false) {
    // Uma atualização substitui a consulta anterior, sem misturar páginas.
    requisicaoImagens?.abort();
    const controller = new AbortController();
    requisicaoImagens = controller;
    const offset = reiniciar ? 0 : offsetImagens;
    atualizarImagens.disabled = true;
    maisImagens.disabled = true;
    statusImagens.textContent = 'Carregando arquivos…';
    try {
        const response = await fetch(`/imagens/?limit=51&offset=${offset}`, {
            signal: controller.signal, cache: 'no-store'
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const imagens = await response.json();
        if (!Array.isArray(imagens)) throw new Error('Resposta inválida');
        if (controller.signal.aborted) return;
        if (reiniciar) listaImagens.replaceChildren();
        for (const imagem of imagens.slice(0, 50)) {
            const item = document.createElement('li');
            const tamanho = (imagem.tamanho_bytes / 1024 / 1024).toLocaleString('pt-BR', {
                maximumFractionDigits: 2
            });
            // textContent evita interpretar nomes de arquivo como HTML.
            item.textContent = `#${imagem.id} — ${imagem.nome_original} — ${tamanho} MB`;
            const visualizar = document.createElement('button');
            visualizar.type = 'button';
            visualizar.textContent = 'Visualizar';
            visualizar.addEventListener('click', () => visualizarImagem(imagem));
            item.append(' ', visualizar);
            listaImagens.appendChild(item);
        }
        offsetImagens = offset + Math.min(imagens.length, 50);
        maisImagens.hidden = imagens.length <= 50;
        statusImagens.textContent = offsetImagens === 0
            ? 'Nenhum arquivo adicionado ainda.'
            : `${offsetImagens} arquivo(s) exibido(s).`;
    } catch (error) {
        if (error.name !== 'AbortError') {
            statusImagens.textContent = 'Não foi possível atualizar a lista. Clique em Atualizar lista para tentar novamente.';
        }
    } finally {
        if (requisicaoImagens === controller) {
            atualizarImagens.disabled = false;
            maisImagens.disabled = false;
        }
    }
}

atualizarImagens.addEventListener('click', () => carregarImagens(true));
maisImagens.addEventListener('click', () => carregarImagens());
carregarImagens(true);


let pedidoPrevia;
let urlPrevia;
async function visualizarImagem(imagem) {
    pedidoPrevia?.abort();
    const controller = new AbortController();
    pedidoPrevia = controller;
    const img = document.getElementById('imagem_previa');
    const status = document.getElementById('status_previa');
    document.getElementById('visualizacao').hidden = false;
    document.getElementById('titulo_previa').textContent = imagem.nome_original;
    img.hidden = true;
    img.removeAttribute('src');
    if (urlPrevia) URL.revokeObjectURL(urlPrevia);
    status.textContent = 'Gerando prévia…';
    try {
        const response = await fetch(`/imagens/${imagem.id}/previa`, {signal: controller.signal});
        if (!response.ok) {
            const data = await response.json().catch(() => null);
            throw new Error(typeof data?.detail === 'string' ? data.detail : 'Não foi possível carregar a prévia.');
        }
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        urlPrevia = URL.createObjectURL(blob);
        img.onload = () => {
            if (pedidoPrevia !== controller) return;
            img.hidden = false;
            status.textContent = 'Prévia carregada.';
        };
        img.onerror = () => { status.textContent = 'Não foi possível exibir a prévia.'; };
        img.src = urlPrevia;
        img.alt = `Prévia de ${imagem.nome_original}`;
    } catch (error) {
        if (error.name !== 'AbortError') status.textContent = error.message;
    }
}
