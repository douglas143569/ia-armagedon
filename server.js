// ARMAGEDON - Hub Server
// Serve a interface web e faz proxy para Ollama

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const os = require('os');
const { execFile, spawn } = require('child_process');

const PORT = 3000;
const OLLAMA_URL = 'http://localhost:11434';
// Gerador de vídeo: local por padrão; aponte pra GPU alugada com ARMAGEDON_VIDEO_URL
// (ex: ARMAGEDON_VIDEO_URL=http://SEU_POD:5001). Ver gpu-video/README-GPU.md
const VIDEO_URL = (process.env.ARMAGEDON_VIDEO_URL || 'http://localhost:5001').replace(/\/$/, '');
const AUDIO_PORT = 5005; // tts_generator.py (5002 é do cérebro, 5003 do assistente de voz, 5004 da memória)
const GEN_PORTS = { imagem: 5000, 'vídeo': 5001, 'áudio': AUDIO_PORT };
// Pastas onde os geradores locais salvam (image_generator.py / video_generator.py)
const MEDIA_DIRS = {
    images: path.join(__dirname, 'images_generated'),
    videos: path.join(__dirname, 'videos_generated'),
};
const MEDIA_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
    '.gif': 'image/gif', '.mp4': 'video/mp4', '.webm': 'video/webm',
};
const financas = require('./financas');

const VOICE_PORT = 5003; // armagedon_voice.py
const PYTHON = process.platform === 'win32' ? 'python' : 'python3';

let voiceProc = null; // processo do assistente de voz iniciado pela página

// Encaminha uma requisição para a API do assistente de voz
function voiceRequest(method, apiPath, body) {
    return new Promise((resolve) => {
        const data = body ? JSON.stringify(body) : null;
        const r = http.request({
            host: '127.0.0.1', port: VOICE_PORT, path: apiPath, method, timeout: 5000,
            headers: data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {},
        }, (resp) => {
            let d = '';
            resp.on('data', c => d += c);
            resp.on('end', () => { try { resolve({ code: resp.statusCode, json: JSON.parse(d) }); } catch { resolve(null); } });
        });
        r.on('error', () => resolve(null));
        r.on('timeout', () => { r.destroy(); resolve(null); });
        if (data) r.write(data);
        r.end();
    });
}

function readBody(req) {
    return new Promise((resolve) => {
        let b = '';
        req.on('data', c => b += c);
        req.on('end', () => { try { resolve(b ? JSON.parse(b) : {}); } catch { resolve({}); } });
    });
}

// Repasse em fluxo para um serviço local (corpo e resposta não passam inteiros pela memória; Range incluído)
function streamProxy(req, res, port, targetPath, offlineMsg) {
    const headers = {};
    for (const h of ['content-type', 'content-length', 'range']) {
        if (req.headers[h]) headers[h] = req.headers[h];
    }
    const pReq = http.request({ host: '127.0.0.1', port, path: targetPath, method: req.method, headers, timeout: 10 * 60 * 1000 }, (pRes) => {
        const out = { 'Cache-Control': 'no-cache' };
        for (const h of ['content-type', 'content-length', 'content-range', 'accept-ranges', 'content-disposition', 'x-vozes', 'x-duracao']) {
            if (pRes.headers[h]) out[h] = pRes.headers[h];
        }
        res.writeHead(pRes.statusCode, out);
        pRes.pipe(res);
    });
    pReq.on('error', () => sendJson(res, 503, { error: offlineMsg }));
    pReq.on('timeout', () => { pReq.destroy(); sendJson(res, 504, { error: 'timeout' }); });
    res.on('close', () => { if (!res.writableEnded) pReq.destroy(); });
    req.pipe(pReq);
}

// ===== Serviço de memória: o hub inicia e mantém no ar (a página e o assistente de voz dependem dele) =====
const MEMORY_PORT = 5004;
let memoryProc = null;
let shuttingDown = false;

function startMemoryService() {
    if (shuttingDown) return;
    const probe = http.get({ host: '127.0.0.1', port: MEMORY_PORT, path: '/health', timeout: 3000 }, (r) => {
        r.resume();
        console.log('[memória] já estava rodando');   // outra instância (ex.: aberta à mão)
    });
    probe.on('timeout', () => probe.destroy());
    probe.on('error', () => {
        memoryProc = spawn(PYTHON, ['-u', path.join(__dirname, 'memory_service.py')], {
            cwd: __dirname, env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, windowsHide: true,
        });
        memoryProc.stdout.on('data', d => process.stdout.write('[memória] ' + d));
        memoryProc.stderr.on('data', d => {
            const text = d.toString();
            if (!/WARNING: This is a development server|Press CTRL\+C|Running on/.test(text)) process.stderr.write('[memória] ' + text);
        });
        memoryProc.on('exit', (code) => {
            memoryProc = null;
            if (!shuttingDown) {
                console.log(`[memória] encerrou (código ${code}); reiniciando em 5 s...`);
                setTimeout(startMemoryService, 5000);
            }
        });
    });
}

// ===== Ollama: se fechar (ex.: depois de se atualizar sozinho), o hub abre de novo =====
const OLLAMA_APP = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Ollama', 'ollama app.exe');
let ollamaLastStart = 0;

function watchOllama() {
    const probe = http.get({ host: '127.0.0.1', port: 11434, path: '/api/version', timeout: 4000 }, (r) => r.resume());
    probe.on('timeout', () => probe.destroy());
    probe.on('error', () => {
        if (Date.now() - ollamaLastStart < 120000) return;   // já mandou abrir: espera subir
        ollamaLastStart = Date.now();
        const app = fs.existsSync(OLLAMA_APP);
        console.log(`[ollama] fechado — ${app ? 'abrindo o aplicativo do Ollama' : 'iniciando "ollama serve"'} de novo`);
        try {
            const child = app
                ? spawn(OLLAMA_APP, [], { detached: true, stdio: 'ignore' })
                : spawn('ollama', ['serve'], { detached: true, stdio: 'ignore', windowsHide: true });
            child.on('error', (e) => console.error('[ollama] não consegui abrir:', e.message));
            child.unref();
        } catch (e) {
            console.error('[ollama] não consegui abrir:', e.message);
        }
    });
}

function sendJson(res, code, obj) {
    if (res.headersSent) {   // a resposta já tinha começado (ex.: navegador cancelou um vídeo): só encerra
        res.destroy();
        return;
    }
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(obj));
}

// --- Amostragem de GPU (Windows perf counters), com cache pra não pesar ------
let _gpuCache = { ts: 0, data: null };
// saída: "<util>;<dedicada_MB>;<compartilhada_MB>" com ponto decimal (cultura invariante)
const GPU_PS = "$ci=[Globalization.CultureInfo]::InvariantCulture;" +
    "$eu=[double](((Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -EA SilentlyContinue).CounterSamples|Measure-Object CookedValue -Sum).Sum);" +
    "$d=[double](((Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -EA SilentlyContinue).CounterSamples|Measure-Object CookedValue -Sum).Sum);" +
    "$s=[double](((Get-Counter '\\GPU Adapter Memory(*)\\Shared Usage' -EA SilentlyContinue).CounterSamples|Measure-Object CookedValue -Sum).Sum);" +
    "$eu.ToString('F1',$ci)+';'+($d/1MB).ToString('F0',$ci)+';'+($s/1MB).ToString('F0',$ci)";

const num = (x) => { const n = Number(x); return Number.isFinite(n) ? n : 0; };

function getGpu() {
    return new Promise((resolve) => {
        if (process.platform !== 'win32') return resolve(null);
        if (Date.now() - _gpuCache.ts < 4500) return resolve(_gpuCache.data);
        execFile('powershell', ['-NoProfile', '-NonInteractive', '-Command', GPU_PS],
            { timeout: 8000, windowsHide: true }, (err, stdout) => {
                if (err || !stdout) { _gpuCache = { ts: Date.now(), data: null }; return resolve(null); }
                const [util, ded, shr] = stdout.trim().split(';');
                const data = {
                    util_pct: Math.round(num(util) * 10) / 10,
                    mem_dedicada_mb: num(ded),
                    mem_compartilhada_mb: num(shr),
                };
                _gpuCache = { ts: Date.now(), data };
                resolve(data);
            });
    });
}

const _vu = new URL(VIDEO_URL);

// GET JSON de um serviço; resolve com null se estiver offline
function getJson(port, path, host = 'localhost') {
    return new Promise((resolve) => {
        const r = http.request({ host, port, path, method: 'GET', timeout: 5000 }, (resp) => {
            let d = '';
            resp.on('data', c => d += c);
            resp.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve(null); } });
        });
        r.on('error', () => resolve(null));
        r.on('timeout', () => { r.destroy(); resolve(null); });
        r.end();
    });
}

// POST JSON pra um serviço local; resolve com null se offline/erro
function postJson(port, path, obj, timeoutMs = 20000) {
    return new Promise((resolve) => {
        const payload = JSON.stringify(obj);
        const r = http.request({
            host: 'localhost', port, path, method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
            timeout: timeoutMs,
        }, (resp) => {
            let d = '';
            resp.on('data', c => d += c);
            resp.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve(null); } });
        });
        r.on('error', () => resolve(null));
        r.on('timeout', () => { r.destroy(); resolve(null); });
        r.write(payload);
        r.end();
    });
}

const BRAIN_PORT = 5002;

const server = http.createServer(async (req, res) => {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    // Métricas: RAM do sistema + GPU + tamanho dos modelos no Ollama
    if (req.url === '/api/metrics' && req.method === 'GET') {
        const totalB = os.totalmem(), freeB = os.freemem();
        const usedB = totalB - freeB;
        const [gpu, ps] = await Promise.all([getGpu(), getJson(11434, '/api/ps')]);
        const modelosB = (ps && ps.models || []).reduce((a, m) => a + (m.size || 0), 0);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            ram: {
                total_gb: +(totalB / 1073741824).toFixed(1),
                usada_gb: +(usedB / 1073741824).toFixed(1),
                livre_gb: +(freeB / 1073741824).toFixed(1),
                pct: Math.round(usedB / totalB * 100),
            },
            modelos_ollama_gb: +(modelosB / 1073741824).toFixed(1),
            gpu: gpu,   // pode ser null (não-Windows ou contador indisponível)
        }));
        return;
    }

    // Status de todos os serviços (pro painel lateral da interface)
    if (req.url === '/api/status' && req.method === 'GET') {
        const [ver, ps, brain, image, video] = await Promise.all([
            getJson(11434, '/api/version'),
            getJson(11434, '/api/ps'),
            getJson(5002, '/health'),
            getJson(5000, '/health'),
            getJson(_vu.port || 5001, '/health', _vu.hostname),
        ]);
        const loaded = (ps && ps.models || []).map(m => m.name);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            hub: true,
            ollama: !!ver,
            ollama_version: ver && ver.version || null,
            modelos_carregados: loaded,
            cerebro: !!brain,
            imagem: !!image,
            video: !!video,
        }));
        return;
    }

    // Lista unificada de processos (imagem + vídeo + áudio)
    if (req.url === '/api/processes' && req.method === 'GET') {
        const [img, vid, aud] = await Promise.all([
            getJson(5000, '/jobs'),
            getJson(_vu.port || 5001, '/jobs', _vu.hostname),
            getJson(AUDIO_PORT, '/jobs'),
        ]);
        const out = {
            servers: { imagem: img !== null, 'vídeo': vid !== null, 'áudio': aud !== null },
            jobs: [
                ...((img && img.jobs) || []).map(j => ({ ...j, server: 'imagem' })),
                ...((vid && vid.jobs) || []).map(j => ({ ...j, server: 'vídeo' })),
                ...((aud && aud.jobs) || []).map(j => ({ ...j, server: 'áudio' })),
            ].sort((a, b) => (b.active - a.active) || (a.elapsed - b.elapsed)),
        };
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(out));
        return;
    }

    // Cancelar um processo: body { server: 'imagem'|'vídeo', job_id }
    if (req.url === '/api/cancel' && req.method === 'POST') {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => {
            let parsed;
            try { parsed = JSON.parse(body); } catch { parsed = {}; }
            const port = GEN_PORTS[parsed.server];
            if (!port || !parsed.job_id) {
                res.writeHead(400);
                res.end(JSON.stringify({ error: 'server ou job_id inválido' }));
                return;
            }
            const host = parsed.server === 'vídeo' ? _vu.hostname : 'localhost';
            const cPort = parsed.server === 'vídeo' ? (_vu.port || 5001) : port;
            const cReq = http.request(
                { host, port: cPort, path: `/cancel/${parsed.job_id}`, method: 'POST', timeout: 10000 },
                (cRes) => {
                    let d = '';
                    cRes.on('data', c => d += c);
                    cRes.on('end', () => {
                        res.writeHead(cRes.statusCode || 200, { 'Content-Type': 'application/json' });
                        res.end(d || JSON.stringify({ ok: true }));
                    });
                }
            );
            cReq.on('error', (e) => { res.writeHead(503); res.end(JSON.stringify({ error: e.message })); });
            cReq.on('timeout', () => { cReq.destroy(); res.writeHead(504); res.end(JSON.stringify({ error: 'timeout' })); });
            cReq.end();
        });
        return;
    }

    // Minhas finanças (dados locais em financas_data/)
    if (await financas.handle(req, res)) return;

    // Montagem de vídeos → gerador (porta 5000). Repasse em fluxo: uploads grandes não passam pela memória
    // e o player de vídeo pode pedir trechos (Range)
    if (req.url.startsWith('/api/videos/')) {
        streamProxy(req, res, 5000, '/videos/' + req.url.slice('/api/videos/'.length), 'Gerador de imagens/vídeos offline');
        return;
    }

    // Direção de voz (texto/diálogo → áudio com emoção e uma voz por personagem) → gerador (porta 5000)
    if (req.url.startsWith('/api/direction/')) {
        streamProxy(req, res, 5000, '/direction/' + req.url.slice('/api/direction/'.length), 'Gerador offline');
        return;
    }

    // Memória de longo prazo → memory_service.py (porta 5004)
    if (req.url.startsWith('/api/memory/')) {
        streamProxy(req, res, MEMORY_PORT, '/' + req.url.slice('/api/memory/'.length), 'Serviço de memória offline');
        return;
    }

    // Sequências (carrossel, HQ, movimento, evolução, storyboard) → gerador de imagens
    if (req.url.startsWith('/api/sequence/')) {
        const target = '/sequence/' + req.url.slice('/api/sequence/'.length);
        const chunks = [];
        req.on('data', c => chunks.push(c));
        req.on('end', () => {
            const body = Buffer.concat(chunks);
            const sReq = http.request({
                host: '127.0.0.1', port: 5000, path: target, method: req.method, timeout: 60000,
                headers: body.length ? { 'Content-Type': 'application/json', 'Content-Length': body.length } : {},
            }, (sRes) => {
                res.writeHead(sRes.statusCode, { 'Content-Type': sRes.headers['content-type'] || 'application/json' });
                sRes.pipe(res);
            });
            sReq.on('error', () => sendJson(res, 503, { error: 'Gerador de imagens offline' }));
            sReq.on('timeout', () => { sReq.destroy(); sendJson(res, 504, { error: 'timeout' }); });
            if (body.length) sReq.write(body);
            sReq.end();
        });
        return;
    }

    // Arquivo de imagem gerada e lista de modelos do gerador
    if ((req.url.startsWith('/api/image-file/') || req.url === '/api/image-models') && req.method === 'GET') {
        // aceita subpastas (sequences/<id>/quadro_01.png) e ignora ?v=... (só serve para evitar cache)
        const filePath = req.url.split('?')[0].slice('/api/image-file/'.length);
        const target = req.url === '/api/image-models'
            ? '/models'
            : '/image/' + filePath.split('/').map(p => encodeURIComponent(decodeURIComponent(p))).join('/');
        // repassa pedidos parciais (Range): o player de vídeo precisa disso para avançar/voltar
        const headers = req.headers.range ? { Range: req.headers.range } : {};
        const fReq = http.request({ host: '127.0.0.1', port: 5000, path: target, method: 'GET', timeout: 30000, headers }, (fRes) => {
            const out = {
                'Content-Type': fRes.headers['content-type'] || 'application/octet-stream',
                'Cache-Control': 'no-cache',
            };
            for (const h of ['content-length', 'content-range', 'accept-ranges']) {
                if (fRes.headers[h]) out[h] = fRes.headers[h];
            }
            res.writeHead(fRes.statusCode, out);
            fRes.pipe(res);
        });
        req.on('close', () => fReq.destroy());   // navegador desistiu: cancela o repasse também
        fReq.on('error', () => sendJson(res, 503, { error: 'Gerador de imagens offline' }));
        fReq.on('timeout', () => { fReq.destroy(); sendJson(res, 504, { error: 'timeout' }); });
        fReq.end();
        return;
    }

    // Proxy status imagens
    if (req.url.startsWith('/api/image-status/') && req.method === 'GET') {
        const jobId = req.url.split('/').pop();
        const sReq = http.request(
            `http://localhost:5000/status/${jobId}`,
            { method: 'GET', timeout: 30000 },
            (sRes) => {
                let data = '';
                sRes.on('data', chunk => data += chunk);
                sRes.on('end', () => {
                    res.writeHead(sRes.statusCode, { 'Content-Type': 'application/json' });
                    res.end(data);
                });
            }
        );
        sReq.on('error', () => { res.writeHead(503); res.end(JSON.stringify({ error: 'Servidor offline' })); });
        sReq.on('timeout', () => { sReq.destroy(); res.writeHead(504); res.end(JSON.stringify({ error: 'timeout' })); });
        sReq.end();
        return;
    }

    // Proxy status vídeos
    if (req.url.startsWith('/api/video-status/') && req.method === 'GET') {
        const jobId = req.url.split('/').pop();
        const videoReq = http.request(
            `${VIDEO_URL}/status/${jobId}`,
            { method: 'GET', timeout: 30000 },
            (videoRes) => {
                let data = '';
                videoRes.on('data', chunk => data += chunk);
                videoRes.on('end', () => {
                    res.writeHead(videoRes.statusCode, { 'Content-Type': 'application/json' });
                    res.end(data);
                });
            }
        );
        videoReq.on('error', () => {
            res.writeHead(503);
            res.end(JSON.stringify({ error: 'Servidor offline' }));
        });
        videoReq.end();
        return;
    }

    // Proxy para gerador de vídeos
    if (req.url === '/api/generate-video' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('error', (err) => {
            res.writeHead(400);
            res.end(JSON.stringify({ error: 'Erro ao ler requisição' }));
        });
        req.on('end', () => {
            if (!body) {
                res.writeHead(400);
                res.end(JSON.stringify({ error: 'Body vazio' }));
                return;
            }
            const videoReq = http.request(
                `${VIDEO_URL}/generate`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Content-Length': Buffer.byteLength(body)
                    },
                    timeout: 1800000
                },
                (videoRes) => {
                    let responseData = '';
                    videoRes.on('data', chunk => { responseData += chunk; });
                    videoRes.on('end', () => {
                        res.writeHead(videoRes.statusCode || 200, { 'Content-Type': 'application/json' });
                        res.end(responseData || JSON.stringify({ error: 'Vazio' }));
                    });
                }
            );
            videoReq.on('error', (err) => {
                res.writeHead(503);
                res.end(JSON.stringify({ error: 'Gerador de vídeos offline: ' + err.message }));
            });
            videoReq.on('timeout', () => {
                videoReq.destroy();
                res.writeHead(504);
                res.end(JSON.stringify({ error: 'Timeout' }));
            });
            videoReq.write(body);
            videoReq.end();
        });
        return;
    }

    // Proxy para gerador de imagens
    if (req.url === '/api/generate-image' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('error', (err) => {
            res.writeHead(400);
            res.end(JSON.stringify({ error: 'Erro ao ler requisição' }));
        });
        req.on('end', () => {
            if (!body) {
                res.writeHead(400);
                res.end(JSON.stringify({ error: 'Body vazio' }));
                return;
            }
            const imageReq = http.request(
                'http://localhost:5000/generate',
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Content-Length': Buffer.byteLength(body)
                    },
                    timeout: 600000
                },
                (imageRes) => {
                    let responseData = '';
                    imageRes.on('data', chunk => { responseData += chunk; });
                    imageRes.on('end', () => {
                        res.writeHead(imageRes.statusCode || 200, { 'Content-Type': 'application/json' });
                        res.end(responseData || JSON.stringify({ error: 'Vazio' }));
                    });
                }
            );
            imageReq.on('error', (err) => {
                res.writeHead(503);
                res.end(JSON.stringify({ error: 'Gerador offline: ' + err.message }));
            });
            imageReq.on('timeout', () => {
                imageReq.destroy();
                res.writeHead(504);
                res.end(JSON.stringify({ error: 'Timeout' }));
            });
            imageReq.write(body);
            imageReq.end();
        });
        return;
    }

    // Passthrough pro cérebro (RAG + memória): /api/brain/<algo> -> localhost:5002/<algo>
    if (req.url.startsWith('/api/brain/')) {
        const target = '/' + req.url.slice('/api/brain/'.length);
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => {
            const opts = {
                host: 'localhost', port: BRAIN_PORT, path: target, method: req.method,
                headers: { 'Content-Type': 'application/json' }, timeout: 600000,
            };
            if (body) opts.headers['Content-Length'] = Buffer.byteLength(body);
            const bReq = http.request(opts, (bRes) => {
                let d = '';
                bRes.on('data', c => d += c);
                bRes.on('end', () => {
                    res.writeHead(bRes.statusCode || 200, { 'Content-Type': 'application/json' });
                    res.end(d || '{}');
                });
            });
            bReq.on('error', (e) => { res.writeHead(503); res.end(JSON.stringify({ error: 'Cérebro offline: ' + e.message })); });
            bReq.on('timeout', () => { bReq.destroy(); res.writeHead(504); res.end(JSON.stringify({ error: 'timeout' })); });
            if (body) bReq.write(body);
            bReq.end();
        });
        return;
    }

    // Proxy pro Ollama (RAG + memória + web + roteador injetados pelo cérebro).
    // Aceita /api/generate (1 turno) e /api/chat (com histórico: payload.messages[]).
    if ((req.url === '/api/generate' || req.url === '/api/chat') && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', async () => {
            let payload;
            try { payload = JSON.parse(body); } catch { payload = null; }

            const isChat = payload && Array.isArray(payload.messages) && payload.messages.length > 0;
            // texto da pergunta atual (última mensagem do usuário, ou o prompt)
            let queryText = '';
            if (isChat) {
                for (let i = payload.messages.length - 1; i >= 0; i--) {
                    if (payload.messages[i].role === 'user') { queryText = payload.messages[i].content || ''; break; }
                }
            } else if (payload && typeof payload.prompt === 'string') {
                queryText = payload.prompt;
            }

            let sources = [];
            let routerModel = '';
            let routerReason = '';
            let webUsed = false;
            const wantsAuto = payload && (payload.model === 'auto' || !payload.model);
            const useWeb = payload && ('use_web' in payload) ? payload.use_web : 'auto';

            if (payload && queryText &&
                (payload.use_rag !== false || wantsAuto || useWeb !== false)) {
                const aug = await postJson(BRAIN_PORT, '/augment', {
                    prompt: queryText,
                    use_rag: payload.use_rag !== false,
                    use_web: useWeb,
                    route: wantsAuto,
                }, 45000);
                if (aug && aug.system_block) {
                    const wrapped = aug.system_block + '\n\n=== PERGUNTA DE DOUGLAS ===\n' + queryText;
                    if (isChat) {
                        for (let i = payload.messages.length - 1; i >= 0; i--) {
                            if (payload.messages[i].role === 'user') { payload.messages[i].content = wrapped; break; }
                        }
                    } else {
                        payload.prompt = wrapped;
                    }
                }
                if (aug) sources = aug.sources || [];
                if (aug && aug.web_usada) webUsed = true;
                if (aug && aug.model) { routerModel = aug.model; routerReason = aug.route_reason || ''; }
            }

            if (wantsAuto) payload.model = routerModel || 'armagedon';
            if (payload) { delete payload.use_rag; delete payload.use_web; }
            const outBody = payload ? JSON.stringify(payload) : body;
            const ollamaPath = isChat ? '/api/chat' : '/api/generate';

            const ollamaReq = http.request(
                `${OLLAMA_URL}${ollamaPath}`,
                { method: 'POST', headers: { 'Content-Type': 'application/json' } },
                (ollamaRes) => {
                    const headers = Object.assign({}, ollamaRes.headers, {
                        'X-Rag-Sources': Buffer.from(JSON.stringify(sources)).toString('base64'),
                        'X-Router-Model': (payload && payload.model) || '',
                        'X-Router-Reason': Buffer.from(routerReason || '', 'utf8').toString('base64'),
                        'X-Web-Used': webUsed ? '1' : '0',
                    });
                    res.writeHead(ollamaRes.statusCode, headers);
                    ollamaRes.pipe(res);
                }
            );
            ollamaReq.on('error', () => {
                res.writeHead(500);
                res.end('Erro ao conectar com Ollama');
            });
            ollamaReq.write(outBody);
            ollamaReq.end();
        });
        return;
    }

    // Mídia gerada (pra interface mostrar o resultado) — só essas duas pastas, sem path traversal
    const media = req.method === 'GET' && req.url.match(/^\/media\/(images|videos)\/([^/?#]+)$/);
    if (media) {
        let name;
        try { name = path.basename(decodeURIComponent(media[2])); } catch { name = ''; }
        const type = MEDIA_TYPES[path.extname(name).toLowerCase()];
        if (!name || !type) { res.writeHead(404); res.end('Não encontrado'); return; }
        fs.readFile(path.join(MEDIA_DIRS[media[1]], name), (err, data) => {
            if (err) { res.writeHead(404); res.end('Não encontrado'); return; }
            // nomes têm timestamp → nunca mudam, pode cachear pra sempre
            res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'public, max-age=31536000, immutable' });
            res.end(data);
        });
        return;
    }

    // Proxy para gerador de voz (TTS)
    if (req.url === '/api/generate-voice' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('error', (err) => {
            res.writeHead(400);
            res.end(JSON.stringify({ error: 'Erro ao ler requisição' }));
        });
        req.on('end', () => {
            if (!body) {
                res.writeHead(400);
                res.end(JSON.stringify({ error: 'Body vazio' }));
                return;
            }
            const voiceReq = http.request(
                `http://localhost:${AUDIO_PORT}/generate`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Content-Length': Buffer.byteLength(body)
                    },
                    timeout: 300000
                },
                (voiceRes) => {
                    let responseData = '';
                    voiceRes.on('data', chunk => { responseData += chunk; });
                    voiceRes.on('end', () => {
                        res.writeHead(voiceRes.statusCode || 200, { 'Content-Type': 'application/json' });
                        res.end(responseData || JSON.stringify({ error: 'Vazio' }));
                    });
                }
            );
            voiceReq.on('error', (err) => {
                res.writeHead(503);
                res.end(JSON.stringify({ error: 'Gerador de voz offline: ' + err.message }));
            });
            voiceReq.on('timeout', () => {
                voiceReq.destroy();
                res.writeHead(504);
                res.end(JSON.stringify({ error: 'Timeout' }));
            });
            voiceReq.write(body);
            voiceReq.end();
        });
        return;
    }

    if (req.url.startsWith('/api/voice-status/') && req.method === 'GET') {
        const jobId = req.url.split('/').pop();
        const voiceReq = http.request(
            `http://localhost:${AUDIO_PORT}/status/${jobId}`,
            { method: 'GET', timeout: 30000 },
            (voiceRes) => {
                let data = '';
                voiceRes.on('data', chunk => data += chunk);
                voiceRes.on('end', () => {
                    res.writeHead(voiceRes.statusCode, { 'Content-Type': 'application/json' });
                    res.end(data);
                });
            }
        );
        voiceReq.on('error', () => {
            res.writeHead(503);
            res.end(JSON.stringify({ error: 'Servidor offline' }));
        });
        voiceReq.end();
        return;
    }

    if (req.url.startsWith('/api/download-voice/') && req.method === 'GET') {
        const jobId = req.url.split('/').pop();
        const voiceReq = http.request(
            `http://localhost:${AUDIO_PORT}/download/${jobId}`,
            { method: 'GET', timeout: 30000 },
            (voiceRes) => {
                if (voiceRes.statusCode === 200) {
                    res.writeHead(200, voiceRes.headers);
                    voiceRes.pipe(res);
                } else {
                    res.writeHead(voiceRes.statusCode);
                    res.end('Arquivo não encontrado');
                }
            }
        );
        voiceReq.on('error', () => {
            res.writeHead(503);
            res.end('Erro ao baixar');
        });
        voiceReq.end();
        return;
    }

    // ===== Assistente de voz (armagedon_voice.py) =====
    if (req.url.startsWith('/api/voice/')) {
        const route = req.url.slice('/api/voice'.length);

        // Liga o assistente (se ainda não estiver rodando)
        if (route === '/start' && req.method === 'POST') {
            const st = await voiceRequest('GET', '/status');
            if (st) return sendJson(res, 200, { running: true, ...st.json });
            if (voiceProc && voiceProc.exitCode === null) return sendJson(res, 200, { running: false, starting: true });

            voiceProc = spawn(PYTHON, ['-u', path.join(__dirname, 'armagedon_voice.py')], {
                cwd: __dirname,
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
                windowsHide: true,
            });
            voiceProc.stdout.on('data', d => process.stdout.write('[voz] ' + d));
            voiceProc.stderr.on('data', d => process.stderr.write('[voz] ' + d));
            voiceProc.on('exit', code => { console.log(`[voz] assistente encerrado (código ${code})`); voiceProc = null; });
            voiceProc.on('error', err => { console.error('[voz] falha ao iniciar:', err.message); voiceProc = null; });
            return sendJson(res, 200, { running: false, starting: true });
        }

        // Desliga o assistente
        if (route === '/stop' && req.method === 'POST') {
            const r = await voiceRequest('POST', '/control', { action: 'shutdown' });
            if (!r && voiceProc) voiceProc.kill();
            return sendJson(res, 200, { running: false });
        }

        // Status / eventos / controle → repassa para a API do Python
        if ((route === '/status' || route.startsWith('/events')) && req.method === 'GET') {
            const r = await voiceRequest('GET', route);
            if (!r) {
                const starting = !!(voiceProc && voiceProc.exitCode === null);
                return sendJson(res, 200, { running: false, starting, state: starting ? 'iniciando' : 'desligado', events: [] });
            }
            return sendJson(res, r.code, { running: true, ...r.json });
        }
        if (route === '/control' && req.method === 'POST') {
            const r = await voiceRequest('POST', '/control', await readBody(req));
            if (!r) return sendJson(res, 503, { running: false, error: 'Assistente de voz desligado' });
            return sendJson(res, r.code, { running: true, ...r.json });
        }

        return sendJson(res, 404, { error: 'rota de voz desconhecida' });
    }

    // Scripts da interface
    if (req.url === '/chat-history.js') {
        fs.readFile(path.join(__dirname, 'chat-history.js'), (err, data) => {
            if (err) { res.writeHead(404); res.end(); return; }
            res.writeHead(200, { 'Content-Type': 'application/javascript; charset=utf-8' });
            res.end(data);
        });
        return;
    }

    // Servir financas.html (Minhas finanças)
    if (req.url === '/financas' || req.url === '/financas.html') {
        fs.readFile(path.join(__dirname, 'financas.html'), (err, data) => {
            if (err) { res.writeHead(404); res.end('Página não encontrada'); return; }
            res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
            res.end(data);
        });
        return;
    }

    // Servir interface-plugins.html
    if (req.url === '/plugins' || req.url === '/interface-plugins.html') {
        const filePath = path.join(__dirname, 'interface-plugins.html');
        fs.readFile(filePath, (err, data) => {
            if (err) {
                res.writeHead(404);
                res.end('Página não encontrada');
                return;
            }
            res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end(data);
        });
        return;
    }

    // Servir interface.html (raiz)
    if (req.url === '/' || req.url === '') {
        const filePath = path.join(__dirname, 'interface.html');
        fs.readFile(filePath, (err, data) => {
            if (err) {
                res.writeHead(404);
                res.end('Página não encontrada');
                return;
            }
            res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end(data);
        });
        return;
    }

    // Plugin endpoints
    if (req.url === '/api/plugins' && req.method === 'GET') {
        // Listar plugins disponíveis
        try {
            const pluginDir = path.join(__dirname, 'plugins');
            if (!fs.existsSync(pluginDir)) {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ plugins: [] }));
                return;
            }

            const plugins = [];
            const dirs = fs.readdirSync(pluginDir);

            for (const dir of dirs) {
                const pluginJsonPath = path.join(pluginDir, dir, 'plugin.json');
                if (fs.existsSync(pluginJsonPath)) {
                    const config = JSON.parse(fs.readFileSync(pluginJsonPath, 'utf-8'));
                    plugins.push({
                        id: dir,
                        name: config.name,
                        version: config.version,
                        description: config.description,
                        enabled: config.enabled || false
                    });
                }
            }

            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ plugins }));
        } catch (err) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: err.message }));
        }
        return;
    }

    // Executar plugin
    if (req.url.startsWith('/api/plugins/') && req.method === 'POST') {
        const parts = req.url.split('/').filter(p => p);
        const pluginId = decodeURIComponent(parts[2] || '');
        const method = decodeURIComponent(parts[3] || 'execute');

        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const params = body ? JSON.parse(body) : {};

                // Executar via plugin_manager.py
                const python = spawn('python3', [
                    path.join(__dirname, 'plugin_executor.py'),
                    pluginId,
                    method,
                    JSON.stringify(params)
                ], { cwd: __dirname });

                let output = '';
                let errorOutput = '';

                python.stdout.on('data', (data) => {
                    output += data.toString();
                });

                python.stderr.on('data', (data) => {
                    errorOutput += data.toString();
                });

                python.on('close', (code) => {
                    try {
                        if (code !== 0) {
                            res.writeHead(400, { 'Content-Type': 'application/json' });
                            res.end(JSON.stringify({
                                success: false,
                                error: errorOutput || 'Erro na execução do plugin'
                            }));
                            return;
                        }
                        const result = JSON.parse(output);
                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify(result));
                    } catch (e) {
                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({
                            success: true,
                            message: 'Plugin executado',
                            output: output.trim()
                        }));
                    }
                });

                python.on('error', (err) => {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        success: false,
                        error: err.message
                    }));
                });
            } catch (err) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    // 404
    res.writeHead(404);
    res.end('Não encontrado');
});

server.listen(PORT, '127.0.0.1', () => {
    startMemoryService();
    watchOllama();
    setInterval(watchOllama, 30000);
    console.log(`
╔════════════════════════════════════════╗
║  ARMAGEDON HUB - Servidor Web          ║
╠════════════════════════════════════════╣
║  🌐 http://localhost:${PORT}              ║
║  🤖 Ollama: ${OLLAMA_URL}        ║
║  ✅ Pronto para conversar!             ║
╚════════════════════════════════════════╝
    `);
});

// Ao fechar o hub, encerra o assistente de voz que ele iniciou
function shutdownVoice() {
    shuttingDown = true;
    if (voiceProc && voiceProc.exitCode === null) voiceProc.kill();
    if (memoryProc && memoryProc.exitCode === null) memoryProc.kill();
}
process.on('exit', shutdownVoice);

// Um erro num repasse não pode derrubar o hub inteiro (a página toda depende dele)
process.on('uncaughtException', (err) => console.error('⚠️  Erro inesperado (hub continua no ar):', err));
process.on('unhandledRejection', (err) => console.error('⚠️  Promessa rejeitada (hub continua no ar):', err));
process.on('SIGINT', () => { shutdownVoice(); process.exit(0); });

server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(`❌ Porta ${PORT} já está em uso!`);
        console.error('Feche outras instâncias ou use outra porta.');
    } else {
        console.error('❌ Erro:', err);
    }
    process.exit(1);
});
