(() => {
    const status = document.getElementById('status_mapa');
    if (!window.L) { status.textContent = 'Não foi possível carregar o mapa. O upload continua disponível.'; return; }
    const mapa = L.map('mapa').setView([-10, -53], 4);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(mapa);
    const botaoImportar = document.getElementById('importar_cena');
    const lista = document.getElementById('cenas_mapa');
    let escolhendo = false, canto = null, area = null, retangulo = null, camada = null, selecionada = null, versao = 0;
    const poligonos = iniciarPoligonos(mapa, () => {
        escolhendo = false; canto = null;
    });
    let importando = false;
    const hoje = new Date();
    const inicio = new Date(hoje); inicio.setDate(inicio.getDate() - 90);
    function dataLocal(d) { return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
    document.getElementById('data_fim').value = dataLocal(hoje);
    document.getElementById('data_inicio').value = dataLocal(inicio);
    function limparCena() {
        versao++;
        selecionada = null; lista.replaceChildren(); botaoImportar.disabled = true;
        if (camada) { mapa.removeLayer(camada); camada = null; }
    }
    document.getElementById('selecionar_area').onclick = () => {
        poligonos.cancelar();
        limparCena(); escolhendo = true; canto = null; area = null;
        if (retangulo) { mapa.removeLayer(retangulo); retangulo = null; }
        document.getElementById('area_mapa').textContent = 'Seleção em andamento.';
        status.textContent = 'Clique no primeiro canto e depois no canto oposto. Área de até 5 km por lado.';
    };
    document.getElementById('limpar_area').onclick = () => {
        limparCena(); area = null; canto = null; escolhendo = false;
        if (retangulo) { mapa.removeLayer(retangulo); retangulo = null; }
        document.getElementById('area_mapa').textContent = 'Nenhuma área selecionada.';
        status.textContent = '';
    };
    mapa.on('click', e => {
        if (!escolhendo) return;
        if (!canto) { canto = e.latlng; status.textContent = 'Agora clique no canto oposto.'; return; }
        const bounds = L.latLngBounds(canto, e.latlng);
        area = {oeste:bounds.getWest(), sul:bounds.getSouth(), leste:bounds.getEast(), norte:bounds.getNorth()};
        if (retangulo) mapa.removeLayer(retangulo);
        retangulo = L.rectangle(bounds, {color:'#c00',weight:2,fillOpacity:.05}).addTo(mapa);
        escolhendo = false; canto = null;
        document.getElementById('area_mapa').textContent = `Área: ${area.sul.toFixed(5)}, ${area.oeste.toFixed(5)} até ${area.norte.toFixed(5)}, ${area.leste.toFixed(5)}`;
        status.textContent = 'Escolha as datas e busque as cenas.';
    });
    async function post(url, body) {
        const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
        const data = await response.json();
        if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(e=>e.msg).join('; ') : (data.detail || 'Falha na consulta.'));
        return data;
    }
    document.getElementById('buscar_cenas').onclick = async () => {
        if (!area) { status.textContent = 'Selecione uma área no mapa primeiro.'; return; }
        limparCena(); const atual = versao;
        const areaBusca = {...area};
        status.textContent = 'Buscando no Earth Engine…';
        try {
            const cenas = await post('/satelite/buscar', {area:areaBusca, inicio:document.getElementById('data_inicio').value, fim:document.getElementById('data_fim').value, nuvens:Number(document.getElementById('nuvens').value)});
            if (atual !== versao) return;
            status.textContent = cenas.length ? 'Escolha uma cena. Nuvens são medidas na cena toda, não só na área selecionada.' : 'Nenhuma cena encontrada. Tente outro período ou limite de nuvens.';
            for (const cena of cenas) {
                const item = document.createElement('li');
                item.textContent = `${new Date(cena.data).toLocaleDateString('pt-BR',{timeZone:'UTC'})} — ${cena.nuvens?.toFixed(1) ?? '?'}% de nuvens — 10 m `;
                const ver = document.createElement('button'); ver.textContent = 'Escolher e ver'; ver.type = 'button';
                ver.onclick = async () => {
                    const pedido = ++versao; selecionada = null; botaoImportar.disabled = true;
                    status.textContent = 'Carregando cena…';
                    try {
                        const body = {area:areaBusca, cena_id:cena.id};
                        const preview = await post('/satelite/previa', body);
                        if (pedido !== versao) return;
                        if (camada) mapa.removeLayer(camada);
                        camada = L.tileLayer(preview.tile_url, {attribution:'Sentinel-2 / Copernicus — Google Earth Engine', maxZoom:19}).addTo(mapa);
                        camada.on('tileerror', () => { status.textContent = 'Falha ao carregar a camada. Escolha a cena novamente para renovar o acesso.'; });
                        selecionada = body; botaoImportar.disabled = importando;
                        status.textContent = `Cena selecionada: ${cena.id}. Confira a imagem no mapa antes de adicionar.`;
                        mapa.fitBounds([[areaBusca.sul,areaBusca.oeste],[areaBusca.norte,areaBusca.leste]]);
                    } catch (error) { if (pedido === versao) status.textContent = error.message; }
                };
                item.appendChild(ver); lista.appendChild(item);
            }
        } catch (error) { if (atual === versao) status.textContent = error.message; }
    };
    botaoImportar.onclick = async () => {
        if (!selecionada || importando) return;
        importando = true; botaoImportar.disabled = true;
        const body = selecionada;
        status.textContent = 'Importando o recorte. Aguarde antes de repetir.';
        try {
            const imagem = await post('/satelite/importar', body);
            status.textContent = `Imagem #${imagem.id} adicionada. Use Recortar na lista de arquivos.`;
            await carregarImagens(true);
        } catch (error) { status.textContent = error.message; }
        finally { importando = false; botaoImportar.disabled = !selecionada; }
    };
    fetch('/satelite/config').then(r=>r.json()).then(c => {
        if (!c.configurado && !area) status.textContent = 'Earth Engine ainda não configurado no servidor. O mapa e o upload local já podem ser usados.';
    }).catch(()=>{ status.textContent = 'Não foi possível verificar a configuração do Earth Engine.'; });
})();
