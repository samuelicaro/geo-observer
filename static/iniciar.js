// A interface é estática; a identidade vem da API.
(async()=>{
    const notice=document.createElement('p');notice.setAttribute('role','status');
    notice.textContent='Conectando ao serviço…';document.body.prepend(notice);
    try {
        const response=await fetch('/auth/eu');
        if(response.status===401) {location.replace('/entrar.html');return;}
        if(!response.ok) throw new Error();
        const user=await response.json();window.geoUsuarioId=user.id;
        for(const source of ['vendor/leaflet/leaflet.js','poligonos.js','mapa.js','upload.js','google-login.js']) {
            await new Promise((resolve,reject)=>{const script=document.createElement('script');
                script.src='/static/'+source;script.onload=resolve;script.onerror=reject;document.body.appendChild(script);});
        }
        notice.remove();
    } catch(error) {notice.textContent='Serviço indisponível. A página está acessível; tente atualizar em instantes.';}
})();
