(() => {
    const panel=document.getElementById('acesso_google');
    const separator=document.getElementById('separador_google');
    const status=document.getElementById('status_google');
    const start=document.getElementById('preparar_google');
    const target=document.getElementById('botao_google');
    let carregamento, enviando=false;
    function carregarGoogle() {
        if (window.google?.accounts?.id) return Promise.resolve();
        if (carregamento) return carregamento;
        carregamento=new Promise((resolve,reject)=>{
            const script=document.createElement('script');
            script.src='https://accounts.google.com/gsi/client'; script.async=true;
            script.onload=resolve;
            script.onerror=()=>{carregamento=null;script.remove();reject(new Error('Não foi possível carregar o Google. Verifique a conexão.'));};
            document.head.appendChild(script);
        });
        return carregamento;
    }
    async function post(url,body) {
        const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const result=await response.json();
        if (!response.ok) throw new Error(typeof result.detail==='string'?result.detail:'Falha na autenticação. Recomece a tentativa.');
        return result;
    }
    start.onclick=async()=>{
        start.disabled=true;target.replaceChildren();
        status.textContent='Preparando acesso ao Google…';
        try {
            await carregarGoogle();
            const mode=window.geoUsuarioId ? 'vincular' : 'entrar';
            const config=await post('/auth/google/iniciar',{modo:mode});
            google.accounts.id.initialize({client_id:config.client_id,nonce:config.nonce,auto_select:false,ux_mode:'popup',
                callback:async data=>{
                    if (enviando) return;
                    enviando=true;start.disabled=true;
                    status.textContent='Validando identidade…';
                    try {
                        await post('/auth/google/concluir',{credential:data.credential});
                        status.textContent=mode==='vincular'?'Google vinculado à sua conta.':'Entrada concluída.';
                        location.href='/';
                    } catch(error) {status.textContent=error.message;target.replaceChildren();start.hidden=false;}
                    finally {enviando=false;start.disabled=false;}
                }});
            google.accounts.id.renderButton(target,{type:'standard',theme:'outline',size:'large',text:'continue_with'});
            start.hidden=true;
            status.textContent=mode==='vincular'?'Escolha a conta Google que deseja vincular à sua conta atual.':'Continue no botão Google. Se já tiver cadastro local, entre com a senha para vinculá-lo.';
        } catch(error) {status.textContent=error.message;target.replaceChildren();start.hidden=false;}
        finally {start.disabled=false;}
    };
    fetch('/auth/google/config').then(r=>r.json()).then(c=>{panel.hidden=!c.disponivel;separator.hidden=!c.disponivel;})
        .catch(()=>{panel.hidden=true;separator.hidden=true;});
})();
