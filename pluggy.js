// ARMAGEDON — Open Finance via Pluggy (Santander e outros bancos), usado por financas.js
// Credenciais e id da conexão ficam em financas_data/pluggy.json (fora do git) ou nas variáveis
// PLUGGY_CLIENT_ID / PLUGGY_CLIENT_SECRET. Nada disso é devolvido ao navegador.
// Só saldo e transações vêm do Pluggy; o resto continua local.

const fs = require('fs');
const path = require('path');

const BASE = (process.env.PLUGGY_BASE_URL || 'https://api.pluggy.ai').replace(/\/$/, '');
const ITEM_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CLIENT_USER_ID = 'armagedon';

const CATEGORIAS = [   // categorias do Pluggy (inglês) → categorias do painel
    [/grocer|supermarket|food and drinks|eating out|restaurant|delivery/i, 'Mercado'],
    [/transport|taxi|ride|fuel|gas station|parking|toll|public transport/i, 'Transporte'],
    [/health|pharmac|doctor|hospital|dentist/i, 'Saúde'],
    [/educat|school|course|tuition/i, 'Educação'],
    [/entertain|leisure|travel|gaming|sport|shopping|clothing/i, 'Lazer'],
    [/subscription|streaming|digital services|telecom|internet|phone/i, 'Assinaturas'],
    [/rent|housing|utilit|electric|water|energy|real estate|insurance/i, 'Moradia'],
    [/loan|interest|tax|fee|credit card payment|debt/i, 'Dívidas'],
];

const datas = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

function categoria(t) {
    if (t.type === 'CREDIT') return 'Receita';
    const c = String(t.category || '');
    const achada = CATEGORIAS.find(([re]) => re.test(c));
    return achada ? achada[1] : 'Outros';
}

// Transação do Pluggy → formato de lançamento do painel. Devolve null para o que não deve entrar.
function normalizar(t) {
    if (!t || !t.id || t.status === 'PENDING') return null;   // pendente muda de id ao ser efetivada
    const valor = Math.abs(Number(t.amount));
    if (!Number.isFinite(valor) || valor <= 0) return null;
    if (t.type !== 'CREDIT' && t.type !== 'DEBIT') return null;
    return {
        ext_id: `pluggy:${t.id}`,
        tipo: t.type === 'CREDIT' ? 'receita' : 'despesa',
        valor,
        data: String(t.date || '').slice(0, 10),
        descricao: String(t.description || t.descriptionRaw || '').trim(),
        categoria: categoria(t),
    };
}

const CLASSES_INVEST = [   // type/subtype do Pluggy → classes do painel
    [/crypto/i, 'Criptomoedas'],
    [/real_estate|fii|fund.*imobili/i, 'Fundos Imobiliários (FIIs)'],
    [/etf/i, 'ETFs'],
    [/stock|equity|bdr|acao|ação/i, 'Ações'],
    [/fixed_income|treasury|cdb|lci|lca|cri|cra|debenture|poupan/i, 'Renda Fixa'],
];

// Investimento do Pluggy → formato do painel. "investido" é o que você aportou; "atual" é o valor de hoje.
function normalizarInvestimento(i, hoje) {
    if (!i || !i.id) return null;
    const atual = Number(i.balance ?? i.value);
    if (!Number.isFinite(atual) || atual < 0) return null;
    const original = Number(i.amountOriginal ?? i.amount);
    const tipo = `${i.type || ''} ${i.subtype || ''}`;
    const achada = CLASSES_INVEST.find(([re]) => re.test(tipo));
    const data = String(i.purchaseDate || i.date || i.issueDate || '').slice(0, 10);
    return {
        ext_id: `pluggy:${i.id}`,
        nome: String(i.name || i.code || 'Investimento').trim().slice(0, 60),
        classe: achada ? achada[1] : 'Outros',
        valor_atual: atual,
        valor_investido: Number.isFinite(original) && original >= 0 ? original : atual,
        data: /^\d{4}-\d{2}-\d{2}$/.test(data) && data <= hoje ? data : hoje,
    };
}

module.exports = function criarPluggy(Erro, dataDir) {
    const arquivo = path.join(dataDir, 'pluggy.json');
    let chave = null;   // { apiKey, expira } — a API key do Pluggy dura 2 h

    function lerEstado() {
        try { return JSON.parse(fs.readFileSync(arquivo, 'utf8')); } catch { return {}; }
    }

    function gravarEstado(e) {
        fs.mkdirSync(dataDir, { recursive: true });
        const tmp = arquivo + '.tmp';
        fs.writeFileSync(tmp, JSON.stringify(e, null, 2), { encoding: 'utf8', mode: 0o600 });
        fs.renameSync(tmp, arquivo);
    }

    function credenciais() {
        if (process.env.PLUGGY_CLIENT_ID && process.env.PLUGGY_CLIENT_SECRET) {
            return { clientId: process.env.PLUGGY_CLIENT_ID, clientSecret: process.env.PLUGGY_CLIENT_SECRET, origem: 'ambiente' };
        }
        const e = lerEstado();
        if (e.clientId && e.clientSecret) return { clientId: e.clientId, clientSecret: e.clientSecret, origem: 'arquivo' };
        return null;
    }

    async function chamar(method, rota, { corpo, apiKey, consulta } = {}) {
        const url = new URL(BASE + rota);
        for (const [k, v] of Object.entries(consulta || {})) url.searchParams.set(k, String(v));
        let r;
        try {
            r = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json', ...(apiKey ? { 'X-API-KEY': apiKey } : {}) },
                body: corpo ? JSON.stringify(corpo) : undefined,
                signal: AbortSignal.timeout(30000),
            });
        } catch { throw new Erro('não consegui falar com o Pluggy (sem internet?)'); }
        const j = await r.json().catch(() => ({}));
        if (!r.ok) {
            if (r.status === 401 || r.status === 403) { chave = null; throw new Erro('o Pluggy recusou as credenciais — confira Client ID e Secret'); }
            if (r.status === 404) throw new Erro('o Pluggy não encontrou o recurso (conexão apagada?)');
            throw new Erro(`erro do Pluggy (${r.status}): ${String(j.message || '').slice(0, 160)}`);
        }
        return j;
    }

    async function autenticar(cred) {
        const j = await chamar('POST', '/auth', { corpo: { clientId: cred.clientId, clientSecret: cred.clientSecret } });
        if (!j.apiKey) throw new Erro('resposta inesperada do Pluggy');
        return j.apiKey;
    }

    async function apiKey() {
        if (chave && chave.expira > Date.now()) return chave.apiKey;
        const cred = credenciais();
        if (!cred) throw new Erro('configure o Client ID e o Secret do Pluggy primeiro');
        chave = { apiKey: await autenticar(cred), expira: Date.now() + 100 * 60 * 1000 };
        return chave.apiKey;
    }

    function status() {
        const cred = credenciais();
        const e = lerEstado();
        return {
            configurado: !!cred,
            origem_credenciais: cred ? cred.origem : null,
            conectado: !!e.itemId,
            banco: e.banco || null,
            ultima_sync: e.ultima_sync || null,
            contas: e.contas || [],
        };
    }

    async function salvarCredenciais(clientId, clientSecret) {
        clientId = String(clientId ?? '').trim();
        clientSecret = String(clientSecret ?? '').trim();
        if (!clientId || !clientSecret || clientId.length > 200 || clientSecret.length > 200) throw new Erro('informe Client ID e Client Secret');
        await autenticar({ clientId, clientSecret });   // só grava se o Pluggy aceitar
        chave = null;
        gravarEstado({ ...lerEstado(), clientId, clientSecret });
        return status();
    }

    // Token de 30 min para o widget de conexão rodar no navegador (não dá acesso aos dados)
    async function connectToken() {
        const e = lerEstado();
        const corpo = { options: { clientUserId: CLIENT_USER_ID, avoidDuplicates: true } };
        if (e.itemId) corpo.itemId = e.itemId;   // reconectar quando a autorização expirou
        const j = await chamar('POST', '/connect_token', { corpo, apiKey: await apiKey() });
        if (!j.accessToken) throw new Erro('resposta inesperada do Pluggy');
        return { accessToken: j.accessToken };
    }

    async function vincular(itemId) {
        if (!ITEM_ID.test(String(itemId))) throw new Erro('id da conexão inválido');
        const item = await chamar('GET', `/items/${itemId}`, { apiKey: await apiKey() });   // confirma que é da sua conta Pluggy
        gravarEstado({ ...lerEstado(), itemId, banco: item.connector?.name || null, ultima_sync: null, contas: [] });
        return status();
    }

    async function buscar(dias) {
        const e = lerEstado();
        if (!e.itemId) throw new Erro('nenhum banco conectado');
        const key = await apiKey();
        const item = await chamar('GET', `/items/${e.itemId}`, { apiKey: key });
        if (item.status === 'UPDATING' || item.status === 'WAITING_USER_INPUT') throw new Erro('o Pluggy ainda está atualizando os dados — tente de novo em alguns instantes');
        if (item.status === 'LOGIN_ERROR' || item.status === 'OUTDATED') throw new Erro('a autorização do banco expirou — reconecte o banco');

        const hoje = new Date();
        const inicio = new Date(hoje);
        if (e.ultima_sync) inicio.setTime(new Date(`${e.ultima_sync}T12:00:00`).getTime() - 7 * 86400000);   // margem p/ lançamentos tardios
        else inicio.setDate(inicio.getDate() - dias);

        const contas = (await chamar('GET', '/accounts', { apiKey: key, consulta: { itemId: e.itemId } })).results || [];
        // Só contas bancárias: lançar compras do cartão E o pagamento da fatura na conta contaria duas vezes.
        const bancarias = contas.filter(c => c.type === 'BANK');
        const transacoes = [];
        for (const c of bancarias) {
            // v2 (o GET /transactions antigo responde 410): páginas de 500 por cursor — o `next` da resposta
            // já vem como "?accountId=...&after=..." e vai colado no caminho para pedir a página seguinte
            let rota = '/v2/transactions';
            let consulta = { accountId: c.id, dateFrom: datas(inicio), dateTo: datas(hoje) };
            for (let pagina = 0; rota && pagina < 40; pagina++) {
                const j = await chamar('GET', rota, { apiKey: key, consulta });
                for (const t of j.results || []) { const n = normalizar(t); if (n) transacoes.push(n); }
                rota = typeof j.next === 'string' && j.next ? '/v2/transactions' + j.next : null;
                consulta = undefined;
            }
        }
        const lista = bancarias.map(c => ({
            nome: String(c.name || c.marketingName || 'Conta').slice(0, 60),
            tipo: c.subtype === 'SAVINGS_ACCOUNT' ? 'poupanca' : 'corrente',
            saldo: Number(c.balance) || 0,
        }));
        const soma = (tipo) => lista.filter(c => c.tipo === tipo).reduce((s, c) => s + c.saldo, 0);

        // Investimentos é um produto à parte: se o banco não compartilhar, o resto da sincronização segue.
        let investimentos = null;
        try {
            investimentos = [];
            for (let pagina = 1, total = 1; pagina <= total && pagina <= 10; pagina++) {
                const j = await chamar('GET', '/investments', { apiKey: key, consulta: { itemId: e.itemId, pageSize: 500, page: pagina } });
                total = j.totalPages || 1;
                for (const i of j.results || []) { const n = normalizarInvestimento(i, datas(hoje)); if (n) investimentos.push(n); }
            }
        } catch { investimentos = null; }

        return {
            transacoes,
            saldo: soma('corrente') + soma('poupanca'),
            saldo_corrente: soma('corrente'),
            saldo_poupanca: soma('poupanca'),
            contas: lista,
            investimentos,
            ignoradasCartao: contas.length - bancarias.length,
            hoje: datas(hoje),
        };
    }

    function concluirSync(r) {
        gravarEstado({ ...lerEstado(), ultima_sync: r.hoje, contas: r.contas });
    }

    async function desconectar() {
        const e = lerEstado();
        if (e.itemId) { try { await chamar('DELETE', `/items/${e.itemId}`, { apiKey: await apiKey() }); } catch { /* segue: o importante é soltar localmente */ } }
        const { itemId, banco, ultima_sync, contas, ...resto } = e;
        gravarEstado(resto);
        return status();
    }

    return { status, salvarCredenciais, connectToken, vincular, buscar, concluirSync, desconectar };
};

module.exports.normalizar = normalizar;
module.exports.normalizarInvestimento = normalizarInvestimento;
