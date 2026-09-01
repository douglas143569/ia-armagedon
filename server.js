// ARMAGEDON - Hub Server
// Serve a interface web e faz proxy para Ollama

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const os = require('os');
const { execFile } = require('child_process');

const PORT = 3000;
const OLLAMA_URL = 'http://localhost:11434';
const GEN_PORTS = { imagem: 5000, 'vídeo': 5001 };

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

// GET JSON de um gerador local; resolve com null se estiver offline
function getJson(port, path) {
    return new Promise((resolve) => {
        const r = http.request({ host: 'localhost', port, path, method: 'GET', timeout: 5000 }, (resp) => {
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
            getJson(5001, '/health'),
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

    // Lista unificada de processos (imagem + vídeo)
    if (req.url === '/api/processes' && req.method === 'GET') {
        const [img, vid] = await Promise.all([
            getJson(5000, '/jobs'),
            getJson(5001, '/jobs'),
        ]);
        const out = {
            servers: { imagem: img !== null, 'vídeo': vid !== null },
            jobs: [
                ...((img && img.jobs) || []).map(j => ({ ...j, server: 'imagem' })),
                ...((vid && vid.jobs) || []).map(j => ({ ...j, server: 'vídeo' })),
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
            const cReq = http.request(
                { host: 'localhost', port, path: `/cancel/${parsed.job_id}`, method: 'POST', timeout: 10000 },
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
            `http://localhost:5001/status/${jobId}`,
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
                'http://localhost:5001/generate',
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

    // Proxy para Ollama API (com RAG + memória injetados pelo cérebro, se disponível)
    if (req.url === '/api/generate' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', async () => {
            let payload;
            try { payload = JSON.parse(body); } catch { payload = null; }

            let sources = [];
            let routerModel = '';
            let routerReason = '';
            let webUsed = false;
            const wantsAuto = payload && (payload.model === 'auto' || !payload.model);
            // use_web: true (sempre) | false (nunca) | ausente => "auto" (heurística)
            const useWeb = payload && ('use_web' in payload)
                ? payload.use_web : 'auto';

            if (payload && typeof payload.prompt === 'string' &&
                (payload.use_rag !== false || wantsAuto || useWeb !== false)) {
                const aug = await postJson(BRAIN_PORT, '/augment', {
                    prompt: payload.prompt,
                    use_rag: payload.use_rag !== false,
                    use_web: useWeb,
                    route: wantsAuto,
                }, 45000);   // web search + fetch de páginas pode passar de 30s
                if (aug && aug.system_block) {
                    payload.prompt = aug.system_block +
                        '\n\n=== PERGUNTA DE DOUGLAS ===\n' + payload.prompt;
                }
                if (aug) sources = aug.sources || [];
                if (aug && aug.web_usada) webUsed = true;
                if (aug && aug.model) { routerModel = aug.model; routerReason = aug.route_reason || ''; }
            }

            // Define o modelo: roteado, ou fallback se o cérebro estiver offline
            if (wantsAuto) payload.model = routerModel || 'armagedon';

            // remove flags internas antes de mandar pro Ollama
            if (payload) { delete payload.use_rag; delete payload.use_web; }
            const outBody = payload ? JSON.stringify(payload) : body;

            const ollamaReq = http.request(
                `${OLLAMA_URL}/api/generate`,
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

    // Servir interface.html
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

    // 404
    res.writeHead(404);
    res.end('Não encontrado');
});

server.listen(PORT, '127.0.0.1', () => {
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

server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(`❌ Porta ${PORT} já está em uso!`);
        console.error('Feche outras instâncias ou use outra porta.');
    } else {
        console.error('❌ Erro:', err);
    }
    process.exit(1);
});
