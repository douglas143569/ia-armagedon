// ARMAGEDON - Hub Server
// Serve a interface web e faz proxy para Ollama

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const { spawn } = require('child_process');

const PORT = 3000;
const OLLAMA_URL = 'http://localhost:11434';
const GEN_PORTS = { imagem: 5000, 'vídeo': 5001, 'áudio': 5002 };
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

function sendJson(res, code, obj) {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(obj));
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

    // Lista unificada de processos (imagem + vídeo + áudio)
    if (req.url === '/api/processes' && req.method === 'GET') {
        const [img, vid, aud] = await Promise.all([
            getJson(5000, '/jobs'),
            getJson(5001, '/jobs'),
            getJson(5002, '/jobs'),
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
        const fReq = http.request({ host: '127.0.0.1', port: 5000, path: target, method: 'GET', timeout: 30000 }, (fRes) => {
            res.writeHead(fRes.statusCode, {
                'Content-Type': fRes.headers['content-type'] || 'application/octet-stream',
                'Cache-Control': 'no-cache',
            });
            fRes.pipe(res);
        });
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

    // Proxy para Ollama API
    if (req.url === '/api/generate' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            const ollamaReq = http.request(
                `${OLLAMA_URL}/api/generate`,
                { method: 'POST', headers: { 'Content-Type': 'application/json' } },
                (ollamaRes) => {
                    res.writeHead(ollamaRes.statusCode, ollamaRes.headers);
                    ollamaRes.pipe(res);
                }
            );
            ollamaReq.on('error', () => {
                res.writeHead(500);
                res.end('Erro ao conectar com Ollama');
            });
            ollamaReq.write(body);
            ollamaReq.end();
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
                'http://localhost:5002/generate',
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
            `http://localhost:5002/status/${jobId}`,
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
            `http://localhost:5002/download/${jobId}`,
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
    if (voiceProc && voiceProc.exitCode === null) voiceProc.kill();
}
process.on('exit', shutdownVoice);
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
