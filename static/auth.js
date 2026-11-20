// Todas as mutações exigem cabeçalho próprio para impedir envio por formulários de outro site.
const originalFetch = window.fetch.bind(window);
window.fetch = (input, options={}) => {
    const headers = new Headers(options.headers);
    if (!['GET','HEAD','OPTIONS'].includes((options.method || 'GET').toUpperCase())) headers.set('X-Geo-Request','1');
    const url=typeof input==='string' && input.startsWith('/') && !input.startsWith('/api/') ? '/api'+input : input;
    return originalFetch(url,{...options,headers}).then(response=>{
        if(response.status===401 && !location.pathname.endsWith('/entrar.html')) location.replace('/entrar.html');
        return response;
    });
};
document.getElementById('sair_conta')?.addEventListener('click',async()=>{
    const response=await fetch('/auth/sair',{method:'POST'});
    if (response.ok) location.href='/entrar.html'; else alert('Não foi possível sair. Tente novamente.');
});
const form=document.getElementById('conta');
form?.addEventListener('submit',async event=>{
    event.preventDefault();
    const status=document.getElementById('status');
    const button=event.submitter || form.querySelector('[value=entrar]');
    if (form.dataset.enviando) return;
    form.dataset.enviando='1';
    form.querySelectorAll('button').forEach(b=>b.disabled=true);
    const email=form.elements.email.value, senha=form.elements.senha.value;
    try {
        const cadastro=button.value==='cadastrar';
        if(cadastro) {
            const response=await fetch('/usuarios/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nome:form.elements.nome.value,email,senha})});
            const data=await response.json();
            if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Confira o nome, e-mail e senha de pelo menos 12 caracteres.');
        }
        const response=await fetch('/auth/entrar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,senha})});
        const data=await response.json();
        if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Não foi possível entrar.');
        form.elements.senha.value=''; location.href='/';
    } catch(error) {status.textContent=error.message;}
    finally {delete form.dataset.enviando; form.querySelectorAll('button').forEach(b=>b.disabled=false);}
});
