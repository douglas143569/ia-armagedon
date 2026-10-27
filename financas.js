// ARMAGEDON — Minhas finanças (API local em /api/financas/*)
// Dados pessoais: ficam só em financas_data/financas.json (fora do git). Nada é enviado para a internet;
// a pergunta à IA vai para o Ollama local.

const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');

const DATA_DIR = process.env.ARMAGEDON_FINANCAS_DIR || path.join(__dirname, 'financas_data');
const DATA_FILE = path.join(DATA_DIR, 'financas.json');
const OLLAMA = { host: '127.0.0.1', port: 11434 };

const CLASSES = ['Ações', 'Fundos Imobiliários (FIIs)', 'Renda Fixa', 'ETFs', 'Criptomoedas', 'Outros'];
const TIPOS = ['receita', 'despesa'];
const MAX_BODY = 100 * 1024;

// ---------- armazenamento ----------
function vazio() {
    return { versao: 1, config: { saldo_inicial: 0 }, lancamentos: [], investimentos: [], metas: [], contas: [] };
}

function carregar() {
    try {
        const d = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
        const base = vazio();
        return { ...base, ...d, config: { ...base.config, ...(d.config || {}) }, contas: Array.isArray(d.contas) ? d.contas : [] };
    } catch (e) {
        if (e.code !== 'ENOENT') console.error('[finanças] arquivo ilegível, começando vazio:', e.message);
        return vazio();
    }
}

function salvar(d) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const tmp = DATA_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(d, null, 2), 'utf8');
    fs.renameSync(tmp, DATA_FILE);   // troca atômica: nunca deixa o arquivo pela metade
}

// ---------- validação ----------
const reais = (v) => Math.round(v * 100) / 100;
const texto = (v, max) => String(v ?? '').trim().slice(0, max);

function numero(v, { min = 0, max = 1e12, campo = 'valor' } = {}) {
    // texto com vírgula = formato brasileiro ("1.234,56"); sem vírgula = número comum ("1234.56")
    const n = typeof v === 'string' ? Number(v.includes(',') ? v.replace(/\./g, '').replace(',', '.') : v) : Number(v);
    if (!Number.isFinite(n)) throw new Erro(`${campo} inválido`);
    if (n < min || n > max) throw new Erro(`${campo} fora do intervalo permitido`);
    return reais(n);
}

class Erro extends Error {}

function hoje() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function dataValida(v) {
    if (v == null || v === '') return hoje();
    const s = String(v);
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) throw new Erro('data inválida (use AAAA-MM-DD)');
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    if (d.getFullYear() !== +m[1] || d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[3]) throw new Erro('data inexistente');
    return s;
}

const novoId = () => crypto.randomBytes(6).toString('hex');

// ---------- cálculos ----------
const mesDe = (data) => data.slice(0, 7);

function vencimentoMensal(inicial, mesesDepois) {
    const [ano, mes, dia] = inicial.split('-').map(Number);
    const ultimoDia = new Date(Date.UTC(ano, mes - 1 + mesesDepois + 1, 0)).getUTCDate();
    const data = new Date(Date.UTC(ano, mes - 1 + mesesDepois, Math.min(dia, ultimoDia)));
    return `${data.getUTCFullYear()}-${String(data.getUTCMonth() + 1).padStart(2, '0')}-${String(data.getUTCDate()).padStart(2, '0')}`;
}

function ehVencimento(conta, data) {
    if (conta.recorrencia === 'unica') return data === conta.vencimento;
    const [ano, mes] = data.split('-').map(Number);
    const [anoBase, mesBase] = conta.vencimento.split('-').map(Number);
    const meses = (ano - anoBase) * 12 + mes - mesBase;
    return meses >= 0 && vencimentoMensal(conta.vencimento, meses) === data;
}

function somaMes(d, mes, tipo) {
    return reais(d.lancamentos.filter(l => l.tipo === tipo && mesDe(l.data) === mes).reduce((s, l) => s + l.valor, 0));
}

function mesAnterior(mes) {
    const [a, m] = mes.split('-').map(Number);
    const x = new Date(a, m - 2, 1);
    return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}`;
}

function variacao(atual, anterior) {
    if (!anterior) return null;             // sem base para comparar
    return reais(((atual - anterior) / Math.abs(anterior)) * 100);
}

function saldoAte(d, limite) {   // limite: 'AAAA-MM-DD' inclusive
    return d.config.saldo_inicial + d.lancamentos
        .filter(l => l.data <= limite)
        .reduce((s, l) => s + (l.tipo === 'receita' ? l.valor : -l.valor), 0);
}

function resumo(d, agora = hoje()) {
    const mes = mesDe(agora);
    const ant = mesAnterior(mes);
    const renda = somaMes(d, mes, 'receita');
    const despesas = somaMes(d, mes, 'despesa');
    const rendaAnt = somaMes(d, ant, 'receita');
    const despesasAnt = somaMes(d, ant, 'despesa');

    const aportado = reais(d.investimentos.reduce((s, i) => s + i.valor_investido, 0));
    const investido = reais(d.investimentos.reduce((s, i) => s + i.valor_atual, 0));
    const saldo = reais(saldoAte(d, '9999-12-31'));
    const patrimonio = reais(saldo + investido);

    // carteira por classe
    const porClasse = CLASSES.map(c => {
        const valor = reais(d.investimentos.filter(i => i.classe === c).reduce((s, i) => s + i.valor_atual, 0));
        return { classe: c, valor, pct: investido > 0 ? reais((valor / investido) * 100) : 0 };
    }).filter(x => x.valor > 0);

    // despesas do mês por categoria
    const cats = {};
    d.lancamentos.filter(l => l.tipo === 'despesa' && mesDe(l.data) === mes)
        .forEach(l => { cats[l.categoria] = reais((cats[l.categoria] || 0) + l.valor); });
    const despesasPorCategoria = Object.entries(cats).map(([categoria, valor]) => ({ categoria, valor }))
        .sort((a, b) => b.valor - a.valor);

    // evolução do patrimônio: últimos 12 meses, a partir do primeiro mês com dados.
    // Meses passados usam o custo dos ativos (aporte); o mês atual usa o valor de hoje.
    const datas = [...d.lancamentos.map(l => l.data), ...d.investimentos.map(i => i.data)].sort();
    const serie = [];
    if (datas.length) {
        const primeiro = mesDe(datas[0]);
        let m = mes;
        const meses = [];
        for (let k = 0; k < 12 && m >= primeiro; k++) { meses.unshift(m); m = mesAnterior(m); }
        for (const mm of meses) {
            const fim = mm + '-31';
            const inv = mm === mes
                ? investido
                : d.investimentos.filter(i => i.data <= fim).reduce((s, i) => s + i.valor_investido, 0);
            serie.push({ mes: mm, patrimonio: reais(saldoAte(d, fim) + inv) });
        }
    }

    return {
        mes, patrimonio, saldo,
        renda, despesas, renda_anterior: rendaAnt, despesas_anterior: despesasAnt,
        renda_var_valor: reais(renda - rendaAnt),
        despesas_var_pct: variacao(despesas, despesasAnt),
        sobra_mes: reais(renda - despesas),
        investido, aportado,
        rentabilidade_pct: aportado > 0 ? reais(((investido - aportado) / aportado) * 100) : null,
        patrimonio_var_pct: serie.length >= 2 ? variacao(serie[serie.length - 1].patrimonio, serie[0].patrimonio) : null,
        carteira: porClasse,
        despesas_por_categoria: despesasPorCategoria,
        evolucao: serie,
    };
}

// Dicas calculadas dos próprios dados (instantâneas, sem IA, sem inventar nada)
function dicas(d, r) {
    const out = [];
    const brl = (v) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    if (!d.lancamentos.length && !d.investimentos.length && !d.metas.length && !d.contas.length) {
        return [{ tipo: 'info', texto: 'Comece registrando suas receitas e despesas do mês em “Planejamento”. As dicas aparecem a partir dos seus números.' }];
    }
    if (r.renda > 0) {
        const taxa = (r.sobra_mes / r.renda) * 100;
        if (taxa < 0) out.push({ tipo: 'aviso', texto: `Neste mês você gastou ${brl(-r.sobra_mes)} a mais do que ganhou. Revise as maiores categorias de despesa.` });
        else if (taxa < 10) out.push({ tipo: 'aviso', texto: `Você está guardando ${taxa.toFixed(0)}% da renda. Uma referência comum é buscar pelo menos 20%.` });
        else if (taxa >= 20) out.push({ tipo: 'ok', texto: `Ótimo: você está guardando ${taxa.toFixed(0)}% da renda deste mês.` });
        else out.push({ tipo: 'info', texto: `Você está guardando ${taxa.toFixed(0)}% da renda. Chegar a 20% é uma boa meta.` });
    }
    if (r.despesas_var_pct != null && r.despesas_var_pct > 10) {
        out.push({ tipo: 'aviso', texto: `Suas despesas subiram ${r.despesas_var_pct.toFixed(0)}% em relação ao mês passado.` });
    }
    const topo = r.despesas_por_categoria[0];
    if (topo && r.despesas > 0 && topo.valor / r.despesas > 0.4 && r.despesas_por_categoria.length > 1) {
        out.push({ tipo: 'info', texto: `“${topo.categoria}” concentra ${((topo.valor / r.despesas) * 100).toFixed(0)}% das despesas do mês.` });
    }
    const baseReserva = r.despesas || r.despesas_anterior;
    if (baseReserva > 0) {
        const meses = Math.max(r.saldo, 0) / baseReserva;
        if (meses < 3) out.push({ tipo: 'aviso', texto: `Seu saldo cobre cerca de ${meses.toFixed(1)} mês(es) de despesas. A reserva de emergência costuma ter de 3 a 6 meses.` });
        else out.push({ tipo: 'ok', texto: `Seu saldo cobre cerca de ${meses.toFixed(1)} meses de despesas.` });
    }
    const maior = r.carteira.slice().sort((a, b) => b.pct - a.pct)[0];
    if (maior && r.carteira.length > 1 && maior.pct > 50) {
        out.push({ tipo: 'aviso', texto: `${maior.pct.toFixed(0)}% da carteira está em ${maior.classe}. Diversificar reduz o risco de depender de uma só classe.` });
    } else if (maior && r.carteira.length === 1 && r.investido > 0) {
        out.push({ tipo: 'info', texto: `Toda a carteira está em ${maior.classe}. Considere diversificar entre classes.` });
    }
    for (const m of d.metas) {
        if (m.alvo > 0 && m.atual >= m.alvo) out.push({ tipo: 'ok', texto: `Meta “${m.nome}” alcançada. Parabéns!` });
    }
    if (!out.length) out.push({ tipo: 'info', texto: 'Tudo em ordem por enquanto. Continue registrando para as dicas ficarem mais precisas.' });
    return out.slice(0, 6);
}

// ---------- IA local ----------
function ollamaJson(method, apiPath, body, timeout) {
    return new Promise((resolve, reject) => {
        const data = body ? JSON.stringify(body) : null;
        const r = http.request({
            ...OLLAMA, path: apiPath, method, timeout,
            headers: data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {},
        }, (resp) => {
            let b = '';
            resp.on('data', c => b += c);
            resp.on('end', () => { try { resolve(JSON.parse(b)); } catch { reject(new Error('resposta inválida do Ollama')); } });
        });
        r.on('error', () => reject(new Error('Ollama offline')));
        r.on('timeout', () => { r.destroy(); reject(new Error('A IA demorou demais para responder')); });
        if (data) r.write(data);
        r.end();
    });
}

async function escolherModelo() {
    const tags = await ollamaJson('GET', '/api/tags', null, 5000);
    const nomes = (tags.models || []).map(m => m.name).filter(n => !/embed|bge|nomic|vl/i.test(n));
    return nomes.find(n => n.startsWith('qwen2.5:7b')) || nomes[0] || null;
}

function contextoFinanceiro(d, r) {
    const f = (v) => v.toFixed(2);
    const linhas = [
        `Mês: ${r.mes}`,
        `Saldo em conta (receitas - despesas acumuladas + saldo inicial): R$ ${f(r.saldo)}`,
        `Receitas do mês: R$ ${f(r.renda)} | Despesas do mês: R$ ${f(r.despesas)} | Sobra: R$ ${f(r.sobra_mes)}`,
        `Receitas mês anterior: R$ ${f(r.renda_anterior)} | Despesas mês anterior: R$ ${f(r.despesas_anterior)}`,
        `Total investido (valor atual): R$ ${f(r.investido)} | Total aportado: R$ ${f(r.aportado)}`,
        `Patrimônio: R$ ${f(r.patrimonio)}`,
        'Carteira: ' + (r.carteira.map(c => `${c.classe} ${c.pct}%`).join(', ') || 'vazia'),
        'Despesas do mês por categoria: ' + (r.despesas_por_categoria.map(c => `${c.categoria} R$ ${f(c.valor)}`).join(', ') || 'nenhuma'),
        'Metas: ' + (d.metas.map(m => `${m.nome} R$ ${f(m.atual)} de R$ ${f(m.alvo)}`).join('; ') || 'nenhuma'),
    ];
    return linhas.join('\n');
}

async function perguntarIA(d, pergunta) {
    const modelo = await escolherModelo();
    if (!modelo) throw new Erro('Nenhum modelo de texto instalado no Ollama');
    const prompt =
        'Você é o assistente financeiro do ARMAGEDON. Responda em português do Brasil, de forma clara e curta (até 8 linhas).\n' +
        'Regras: use SOMENTE os números abaixo quando falar da situação do usuário; se faltar dado, diga o que falta. ' +
        'Não invente cotações nem rentabilidades futuras. Não indique ativos específicos para comprar. ' +
        'Explique conceitos e caminhos; lembre, quando fizer sentido, que isto é orientação educativa e não consultoria financeira.\n\n' +
        `DADOS DO USUÁRIO:\n${contextoFinanceiro(d, resumo(d))}\n\nPERGUNTA: ${pergunta}\n\nRESPOSTA:`;
    const out = await ollamaJson('POST', '/api/generate', { model: modelo, prompt, stream: false, options: { temperature: 0.4 } }, 5 * 60 * 1000);
    const resposta = String(out.response || '').trim();
    if (!resposta) throw new Error('A IA não devolveu resposta');
    return { resposta, modelo };
}

// ---------- rotas ----------
function lerCorpo(req) {
    return new Promise((resolve, reject) => {
        let b = '';
        req.on('data', c => {
            b += c;
            if (b.length > MAX_BODY) { reject(new Erro('corpo grande demais')); req.destroy(); }
        });
        req.on('end', () => { try { resolve(b ? JSON.parse(b) : {}); } catch { reject(new Erro('JSON inválido')); } });
        req.on('error', () => reject(new Erro('requisição interrompida')));
    });
}

function enviar(res, code, obj) {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(obj));
}

// Só a própria página (mesma origem) pode ler/alterar. O hub abre CORS "*" para o resto da API;
// aqui isso exporia os dados financeiros a qualquer site aberto no navegador.
function mesmaOrigem(req) {
    const ok = /^(localhost|127\.0\.0\.1)(:\d+)?$/;
    if (!ok.test(req.headers.host || '')) return false;   // bloqueia DNS rebinding
    const o = req.headers.origin;
    if (!o) return true;
    try { return ok.test(new URL(o).host); } catch { return false; }
}

function resposta(d) {
    const r = resumo(d);
    return { config: d.config, lancamentos: d.lancamentos, investimentos: d.investimentos, metas: d.metas, contas: d.contas, resumo: r, dicas: dicas(d, r), classes: CLASSES };
}

function criarLancamento(b) {
    if (!TIPOS.includes(b.tipo)) throw new Erro('tipo deve ser receita ou despesa');
    const categoria = texto(b.categoria, 40) || (b.tipo === 'receita' ? 'Receita' : 'Outros');
    return {
        id: novoId(), tipo: b.tipo, categoria, descricao: texto(b.descricao, 80),
        valor: numero(b.valor, { min: 0.01, campo: 'valor' }), data: dataValida(b.data),
    };
}

function criarInvestimento(b) {
    if (!CLASSES.includes(b.classe)) throw new Erro('classe inválida');
    const nome = texto(b.nome, 60);
    if (!nome) throw new Erro('informe o nome do ativo');
    const investido = numero(b.valor_investido, { campo: 'valor investido' });
    const atual = b.valor_atual === '' || b.valor_atual == null ? investido : numero(b.valor_atual, { campo: 'valor atual' });
    return { id: novoId(), classe: b.classe, nome, valor_investido: investido, valor_atual: atual, data: dataValida(b.data) };
}

function criarMeta(b) {
    const nome = texto(b.nome, 60);
    if (!nome) throw new Erro('informe o nome da meta');
    return {
        id: novoId(), nome, icone: texto(b.icone, 4) || '🎯',
        alvo: numero(b.alvo, { min: 0.01, campo: 'valor da meta' }),
        atual: b.atual === '' || b.atual == null ? 0 : numero(b.atual, { campo: 'valor atual' }),
    };
}

function criarConta(b) {
    const descricao = texto(b.descricao, 80);
    if (!descricao) throw new Erro('informe o nome da conta');
    if (!['unica', 'mensal'].includes(b.recorrencia)) throw new Erro('frequência deve ser única ou mensal');
    return {
        id: novoId(), descricao,
        valor: numero(b.valor, { min: 0.01, campo: 'valor da conta' }),
        vencimento: dataValida(b.vencimento),
        recorrencia: b.recorrencia,
        pagamentos: [],
    };
}

// Devolve true se tratou a requisição
async function handle(req, res) {
    const u = (req.url || '').split('?')[0];
    if (!u.startsWith('/api/financas')) return false;
    res.removeHeader('Access-Control-Allow-Origin');
    if (!mesmaOrigem(req)) { enviar(res, 403, { error: 'origem não permitida' }); return true; }

    try {
        const partes = u.slice('/api/financas'.length).split('/').filter(Boolean);   // ex.: ['lancamentos', 'ab12']
        const [recurso, id] = partes;
        const d = carregar();
        const m = req.method;

        if (m === 'GET' && recurso === 'dados') { enviar(res, 200, resposta(d)); return true; }

        const colecoes = { lancamentos: criarLancamento, investimentos: criarInvestimento, metas: criarMeta, contas: criarConta };
        if (colecoes[recurso]) {
            if (m === 'POST' && !id) {
                d[recurso].push(colecoes[recurso](await lerCorpo(req)));
            } else if (m === 'DELETE' && id) {
                const antes = d[recurso].length;
                d[recurso] = d[recurso].filter(x => x.id !== id);
                if (d[recurso].length === antes) throw new Erro('item não encontrado');
            } else if (m === 'PUT' && id && recurso === 'contas') {
                const conta = d.contas.find(x => x.id === id);
                if (!conta) throw new Erro('conta não encontrada');
                const pagamento = await lerCorpo(req);
                if (!pagamento.pagar) throw new Erro('informe a data do pagamento');
                const dataPagamento = dataValida(pagamento.pagar);
                if (!ehVencimento(conta, dataPagamento)) throw new Erro('data não corresponde a um vencimento desta conta');
                if (!conta.pagamentos.includes(dataPagamento)) conta.pagamentos.push(dataPagamento);
            } else if (m === 'PUT' && id && recurso !== 'lancamentos') {
                const item = d[recurso].find(x => x.id === id);
                if (!item) throw new Erro('item não encontrado');
                const b = await lerCorpo(req);
                if (recurso === 'investimentos') {
                    if (b.valor_atual != null) item.valor_atual = numero(b.valor_atual, { campo: 'valor atual' });
                    if (b.valor_investido != null) item.valor_investido = numero(b.valor_investido, { campo: 'valor investido' });
                } else {
                    if (b.atual != null) item.atual = numero(b.atual, { campo: 'valor atual' });
                    if (b.alvo != null) item.alvo = numero(b.alvo, { min: 0.01, campo: 'valor da meta' });
                    if (b.somar != null) item.atual = reais(Math.max(0, item.atual + numero(b.somar, { min: -1e12, campo: 'valor' })));
                }
            } else { enviar(res, 405, { error: 'método não permitido' }); return true; }
            salvar(d);
            enviar(res, 200, resposta(d));
            return true;
        }

        if (recurso === 'config' && m === 'PUT') {
            const b = await lerCorpo(req);
            if (b.saldo_inicial != null) d.config.saldo_inicial = numero(b.saldo_inicial, { min: -1e12, campo: 'saldo inicial' });
            salvar(d);
            enviar(res, 200, resposta(d));
            return true;
        }

        if (recurso === 'ia' && m === 'POST') {
            const pergunta = texto((await lerCorpo(req)).pergunta, 1000);
            if (!pergunta) throw new Erro('escreva uma pergunta');
            enviar(res, 200, await perguntarIA(d, pergunta));
            return true;
        }

        enviar(res, 404, { error: 'rota não encontrada' });
    } catch (e) {
        enviar(res, e instanceof Erro ? 400 : 500, { error: e.message });
    }
    return true;
}

module.exports = { handle, resumo, dicas, carregar, vazio, CLASSES, _interno: { criarLancamento, criarInvestimento, criarMeta, criarConta, numero, dataValida, mesAnterior, vencimentoMensal, ehVencimento } };
