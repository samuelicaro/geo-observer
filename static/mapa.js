(() => {
    const status = document.getElementById('status_mapa');
    if (!window.L) { status.textContent = 'Não foi possível carregar o mapa. O upload continua disponível.'; return; }
    const mapa = L.map('mapa').setView([-10, -53], 4);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(mapa);
    let resultadosLayer=null, consultaResultados=0;
    const botaoLimparResultados=document.getElementById('limpar_resultados_mapa');
    botaoLimparResultados.onclick=()=>{
        consultaResultados++;
        if(resultadosLayer) mapa.removeLayer(resultadosLayer);
        resultadosLayer=null; botaoLimparResultados.disabled=true;
        status.textContent='Inferência removida da visualização. Os resultados continuam salvos no processamento.';
    };
    const cores={edificacao:'#c94b45',vegetacao_arborea:'#288b45',agua:'#287dc0',via:'#b88c35'};
    document.addEventListener('mostrar-resultados',async event=>{
        const pedido=++consultaResultados;
        status.textContent='Carregando cobertura prevista…';
        try {
            const features=[];
            for(let offset=0;offset<20000;offset+=1000) {
                const response=await fetch(`/processamentos/${event.detail}/resultados?limit=1000&offset=${offset}`);
                const data=await response.json();
                if(pedido!==consultaResultados) return;
                if(!response.ok) throw new Error(data.detail || 'Falha ao consultar resultados.');
                features.push(...data.features);
                if(!data.mais) break;
            }
            if(resultadosLayer) mapa.removeLayer(resultadosLayer);
            resultadosLayer=L.geoJSON({type:'FeatureCollection',features},{style:f=>({color:cores[f.properties.classe]||'#888',weight:1,fillOpacity:0.5}),
                onEachFeature:(f,layer)=>layer.bindTooltip(`${f.properties.classe}: ${(100*f.properties.confianca).toFixed(1)}% (escore do modelo)`)}).addTo(mapa);
            botaoLimparResultados.disabled=!features.length;
            if(resultadosLayer.getBounds().isValid()) mapa.fitBounds(resultadosLayer.getBounds());
            status.textContent=`Processamento #${event.detail}: ${features.length} polígonos previstos (limite de exibição: 20 mil). Vermelho: edificações; verde: vegetação arbórea; azul: água; ocre: vias. Atualize após o avanço das tarefas. Processamentos antigos podem conter somente recortes.`;
            document.getElementById('mapa').scrollIntoView({behavior:'smooth'});
        } catch(error) {if(pedido===consultaResultados) status.textContent=error.message;}
    });
    const botaoImportar = document.getElementById('importar_cena');
    const lista = document.getElementById('cenas_mapa');
    let escolhendo = false, canto = null, area = null, retangulo = null, camada = null, selecionada = null, versao = 0;
    const poligonos = iniciarPoligonos(mapa, () => {
        escolhendo = false; canto = null;
    });
    let extensaoImagem = null, previaLocal = null, consultaExtensao = 0;
    const infoImagem = document.createElement('p');
    const limparImagem = document.createElement('button');
    limparImagem.type = 'button'; limparImagem.textContent = 'Desmarcar imagem'; limparImagem.hidden = true;
    document.getElementById('mapa').after(infoImagem, limparImagem);
    function desmarcarImagem() {
        consultaExtensao++;
        if (extensaoImagem) mapa.removeLayer(extensaoImagem);
        if (previaLocal) mapa.removeLayer(previaLocal);
        previaLocal = null;
        extensaoImagem = null; poligonos.definirImagem(null);
        infoImagem.textContent = ''; limparImagem.hidden = true;
    }
    limparImagem.onclick = desmarcarImagem;
    document.addEventListener('localizar-imagem', async event => {
        desmarcarImagem(); limparCena();
        const atual = consultaExtensao;
        const imagem = event.detail;
        infoImagem.textContent = 'Buscando localização da imagem…';
        try {
            const response = await fetch(`/imagens/${imagem.id}/extensao`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Não foi possível localizar a imagem.');
            if (atual !== consultaExtensao) return;
            const layer = L.geoJSON(data, {style:{color:'#008040',weight:3,fillOpacity:0},interactive:false});
            if (!layer.getBounds().isValid()) throw new Error('Extensão geográfica inválida.');
            extensaoImagem = layer.addTo(mapa);
            poligonos.cancelar(); poligonos.definirImagem(imagem.id);
            escolhendo = false; canto = null;
            mapa.fitBounds(layer.getBounds(), {padding:[20,20],maxZoom:19});
            infoImagem.textContent = `Imagem #${imagem.id}: ${imagem.nome_original}. Carregando prévia sobre o mapa… Novas áreas terão este ID preenchido; confirme em Salvar no servidor.`;
            limparImagem.hidden = false;
            document.getElementById('mapa').scrollIntoView({behavior:'smooth',block:'center'});
            const previewResponse = await fetch(`/imagens/${imagem.id}/previa-mapa`);
            const preview = await previewResponse.json();
            if (atual !== consultaExtensao) return;
            if (!previewResponse.ok) throw new Error(preview.detail || 'Falha na prévia georreferenciada.');
            previaLocal = L.imageOverlay(preview.imagem_url,preview.bounds,{opacity:0.85,interactive:false}).addTo(mapa);
            infoImagem.textContent = `Imagem #${imagem.id}: ${imagem.nome_original}. Prévia reduzida sobre o mapa; desenhe a área e salve. O arquivo original é preservado.`;
        } catch (error) { if (atual === consultaExtensao) infoImagem.textContent = error.message; }
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
    document.addEventListener('area-cenas-selecionada', event => {
        const geometry=event.detail?.geometry;
        const ring=geometry?.type==='Polygon' && geometry.coordinates?.length===1 ? geometry.coordinates[0] : null;
        if (!ring || ring.length<4) { status.textContent='Esse polígono não tem um contorno válido para buscar cenas.'; return; }
        const pontos=ring.slice(0,-1);
        if (pontos.some(p=>!Array.isArray(p) || p.length<2 || !Number.isFinite(p[0]) || !Number.isFinite(p[1]))) {
            status.textContent='Esse polígono tem coordenadas inválidas.'; return;
        }
        const oeste=Math.min(...pontos.map(p=>p[0])), leste=Math.max(...pontos.map(p=>p[0]));
        const sul=Math.min(...pontos.map(p=>p[1])), norte=Math.max(...pontos.map(p=>p[1]));
        if (sul < -60 || norte > 60 || (leste-oeste)*111.32 > 5 || (norte-sul)*111.32 > 5) {
            status.textContent='A busca Sentinel-2 aceita áreas até cerca de 5 km por lado, entre 60°S e 60°N.'; return;
        }
        const bounds=L.latLngBounds([sul,oeste],[norte,leste]);
        area={oeste,sul,leste,norte}; escolhendo=false; canto=null; limparCena();
        if (retangulo) mapa.removeLayer(retangulo);
        retangulo=L.geoJSON(geometry,{style:{color:'#c00',weight:2,fillOpacity:.08},interactive:false}).addTo(mapa);
        mapa.fitBounds(bounds,{padding:[20,20],maxZoom:19});
        document.getElementById('area_mapa').textContent=`Polígono selecionado: ${event.detail?.nome || 'área desenhada'}.`;
        status.textContent='Área pronta. A busca Sentinel-2 usa o retângulo que envolve o polígono; confira a cena no mapa antes de importar.';
        document.getElementById('area_mapa').scrollIntoView({behavior:'smooth',block:'center'});
    });
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
                        desmarcarImagem();
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
        if (!c.configurado && !area) status.textContent = 'Busca por cenas temporariamente indisponível. O mapa e o envio de GeoTIFF continuam disponíveis.';
    }).catch(()=>{ status.textContent = 'Não foi possível verificar a configuração do Earth Engine.'; });
})();
