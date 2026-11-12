// GeoJSON usa longitude, latitude. O desenho é uma área de interesse, não uma detecção.
function validarAnel(pontos) {
    if (pontos.length < 3 || pontos.length > 200) return 'Marque entre 3 e 200 pontos.';
    if (pontos.some(p => !Number.isFinite(p[0]) || !Number.isFinite(p[1]) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 85)) return 'Desenhe dentro dos limites do mapa principal.';
    if (new Set(pontos.map(p => p.join(','))).size !== pontos.length) return 'Há pontos repetidos. Desfaça o último ponto.';
    const cross = (a,b,c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    const sobre = (a,b,p) => Math.abs(cross(a,b,p)) < 1e-12 && p[0] >= Math.min(a[0],b[0]) && p[0] <= Math.max(a[0],b[0]) && p[1] >= Math.min(a[1],b[1]) && p[1] <= Math.max(a[1],b[1]);
    for (let i=0;i<pontos.length;i++) {
        const a=pontos[i], b=pontos[(i+1)%pontos.length];
        if (Math.abs(a[0]-b[0]) > 180) return 'Não cruze o antimeridiano.';
        const anterior=pontos[(i+pontos.length-1)%pontos.length];
        if (Math.abs(cross(anterior,a,b)) < 1e-12) return 'Remova pontos consecutivos alinhados.';
        for (let j=i+1;j<pontos.length;j++) {
            if (j===i+1 || (i===0 && j===pontos.length-1)) continue;
            const c=pontos[j], d=pontos[(j+1)%pontos.length];
            if ((cross(a,b,c)*cross(a,b,d)<0 && cross(c,d,a)*cross(c,d,b)<0) || sobre(a,b,c) || sobre(a,b,d) || sobre(c,d,a) || sobre(c,d,b)) return 'As bordas não podem se cruzar ou se tocar.';
        }
    }
    return null;
}
function iniciarPoligonos(mapa, aoIniciar) {
    const el = id => document.getElementById(id);
    const mensagem=el('status_poligonos'), lista=el('lista_poligonos');
    const chave='geo-observer.areas.v1';
    let desenhando=false, pontos=[], registros=[], rascunho=null, zoomAnterior=true;
    const camadas=L.layerGroup().addTo(mapa);
    let carregando=false;
    async function pedido(url, options={}) {
        const response=await fetch(url, options);
        const data=response.status===204 ? null : await response.json();
        if (!response.ok) throw new Error(Array.isArray(data?.detail) ? data.detail.map(e=>e.msg).join('; ') : (data?.detail || `Falha HTTP ${response.status}`));
        return data;
    }
    function featureServidor(row) {
        return {type:'Feature',properties:{tipo:'area_interesse',id:row.id,nome:row.nome,imagem_id:row.imagem_id,salvo:true},geometry:row.geometria};
    }
    async function carregarServidor() {
        if (carregando) return;
        carregando=true; el('atualizar_areas').disabled=true;
        try {
            const rows=[];
            for (let offset=0;;offset+=100) {
                const page=await pedido(`/areas/?limit=100&offset=${offset}`);
                rows.push(...page);
                if (page.length<100) break;
            }
            const ids=new Set(rows.map(r=>r.id));
            registros=[...rows.map(featureServidor),...registros.filter(f=>!f.properties.salvo && !ids.has(f.properties.id))];
            renderizar(); mensagem.textContent='Áreas do servidor atualizadas. Rascunhos locais preservados.'; salvar();
        } catch (error) { mensagem.textContent=`Não foi possível atualizar: ${error.message}. Desenhos locais preservados.`; }
        finally { carregando=false; el('atualizar_areas').disabled=false; }
    }
    el('atualizar_areas').onclick=carregarServidor;
    function salvar() {
        try { localStorage.setItem(chave,JSON.stringify(registros)); }
        catch (_) { mensagem.textContent='Não foi possível salvar no navegador. Baixe o GeoJSON para guardar as áreas.'; }
    }
    function atualizarRascunho() {
        if (rascunho) mapa.removeLayer(rascunho);
        rascunho=L.layerGroup().addTo(mapa);
        const latlngs=pontos.map(p=>[p[1],p[0]]);
        L.polyline(latlngs,{color:'#205fa0',interactive:false}).addTo(rascunho);
        latlngs.forEach(p=>L.circleMarker(p,{radius:4,color:'#205fa0',interactive:false}).addTo(rascunho));
        el('desfazer_vertice').disabled=!pontos.length;
        el('concluir_poligono').disabled=pontos.length<3;
    }
    function cancelar() {
        if (!desenhando) return;
        desenhando=false; pontos=[];
        if (rascunho) { mapa.removeLayer(rascunho); rascunho=null; }
        if (zoomAnterior) mapa.doubleClickZoom.enable();
        mapa.getContainer().style.cursor='';
        ['desfazer_vertice','concluir_poligono','cancelar_poligono'].forEach(id=>el(id).disabled=true);
        el('desenhar_poligono').disabled=false;
        mensagem.textContent='Desenho encerrado.';
    }
    function renderizar() {
        camadas.clearLayers(); lista.replaceChildren();
        registros.forEach((feature,index)=>{
            const camada=L.geoJSON(feature,{style:{color:'#205fa0',weight:2,fillOpacity:.15},interactive:false}).addTo(camadas);
            const item=document.createElement('li');
            const props=feature.properties;
            props.id ||= crypto.randomUUID();
            item.textContent=`${props.salvo ? 'Salva no servidor' : 'Rascunho local'} — ${feature.geometry.coordinates[0].length-1} vértices `;
            const nome=document.createElement('input'); nome.value=props.nome || `Área ${index+1}`; nome.maxLength=100; nome.setAttribute('aria-label','Nome da área');
            const imagem=document.createElement('input'); imagem.type='number'; imagem.min='1'; imagem.step='1'; imagem.placeholder='ID da imagem (opcional)'; imagem.value=props.imagem_id ?? ''; imagem.setAttribute('aria-label','ID da imagem associada');
            const guardar=document.createElement('button'); guardar.type='button'; guardar.textContent=props.salvo ? 'Atualizar vínculo/nome' : 'Salvar no servidor';
            guardar.onclick=async()=>{
                if (carregando) return;
                if (!nome.value.trim() || !imagem.checkValidity()) { mensagem.textContent='Preencha o nome e um ID de imagem válido, ou deixe o ID vazio.'; return; }
                carregando=true; guardar.disabled=true; excluir.disabled=true; el('atualizar_areas').disabled=true;
                try {
                    const body={id:props.id,nome:nome.value.trim(),imagem_id:imagem.value ? Number(imagem.value) : null,geometria:feature.geometry};
                    const row=await pedido(props.salvo ? `/areas/${props.id}` : '/areas/',{method:props.salvo ? 'PUT' : 'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                    Object.assign(feature,featureServidor(row));
                    renderizar(); mensagem.textContent='Área salva no servidor.'; salvar();
                } catch (error) { mensagem.textContent=`Falha ao salvar: ${error.message}. Confira a lista antes de repetir.`; }
                finally { carregando=false; guardar.disabled=false; excluir.disabled=false; el('atualizar_areas').disabled=false; }
            };
            const ver=document.createElement('button'); ver.type='button'; ver.textContent='Ver no mapa';
            ver.onclick=()=>mapa.fitBounds(camada.getBounds());
            const excluir=document.createElement('button'); excluir.type='button'; excluir.textContent='Excluir';
            excluir.onclick=async()=>{
                if (carregando) return;
                carregando=true; excluir.disabled=true; guardar.disabled=true;
                try {
                    if (props.salvo) await pedido(`/areas/${props.id}`,{method:'DELETE'});
                    registros=registros.filter(f=>f!==feature); renderizar(); salvar();
                } catch (error) { mensagem.textContent=`Não foi possível excluir: ${error.message}`; }
                finally { carregando=false; excluir.disabled=false; guardar.disabled=false; }
            };
            item.append(nome,imagem,guardar,ver,excluir); lista.appendChild(item);
        });
        el('exportar_poligonos').disabled=!registros.length;
    }
    el('desenhar_poligono').onclick=()=>{
        aoIniciar(); desenhando=true; pontos=[];
        zoomAnterior=mapa.doubleClickZoom.enabled(); mapa.doubleClickZoom.disable();
        mapa.getContainer().style.cursor='crosshair';
        el('desenhar_poligono').disabled=true; el('cancelar_poligono').disabled=false;
        mensagem.textContent='Clique nos vértices e depois em Concluir. Não repita o primeiro ponto.';
    };
    mapa.on('click',e=>{
        if (!desenhando) return;
        if (pontos.length>=200) { mensagem.textContent='Limite de 200 pontos. Conclua ou desfaça.'; return; }
        pontos.push([e.latlng.lng,e.latlng.lat]); atualizarRascunho();
        mensagem.textContent=`${pontos.length} pontos. Continue ou clique em Concluir.`;
    });
    el('desfazer_vertice').onclick=()=>{pontos.pop(); atualizarRascunho(); mensagem.textContent=`${pontos.length} pontos.`;};
    el('cancelar_poligono').onclick=cancelar;
    el('concluir_poligono').onclick=()=>{
        const erro=validarAnel(pontos);
        if (erro) { mensagem.textContent=erro; return; }
        registros.push({type:'Feature',properties:{tipo:'area_interesse',id:crypto.randomUUID(),salvo:false},geometry:{type:'Polygon',coordinates:[[...pontos,[...pontos[0]]]]}});
        cancelar(); renderizar(); mensagem.textContent='Área criada. Ainda não há predição vinculada.'; salvar();
    };
    el('exportar_poligonos').onclick=()=>{
        const blob=new Blob([JSON.stringify({type:'FeatureCollection',features:registros},null,2)],{type:'application/geo+json'});
        const url=URL.createObjectURL(blob), link=document.createElement('a');
        link.href=url; link.download='areas-interesse.geojson'; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    try {
        const salvo=JSON.parse(localStorage.getItem(chave)||'[]');
        if (!Array.isArray(salvo)) throw new Error('Formato inválido');
        registros=salvo.filter(f=>f?.type==='Feature' && f.geometry?.type==='Polygon' && f.geometry.coordinates?.length===1 && Array.isArray(f.geometry.coordinates[0]) && f.geometry.coordinates[0].every(p=>Array.isArray(p)&&p.length===2) && !validarAnel(f.geometry.coordinates[0].slice(0,-1)) && JSON.stringify(f.geometry.coordinates[0][0])===JSON.stringify(f.geometry.coordinates[0].at(-1)));
    } catch (_) { mensagem.textContent='Não foi possível recuperar as áreas salvas neste navegador.'; }
    registros.forEach(f=>{ f.properties ||= {}; f.properties.id ||= crypto.randomUUID(); });
    renderizar(); salvar(); carregarServidor();
    return {cancelar};
}
