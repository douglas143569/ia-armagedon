// ARMAGEDON - Hub Server
// Serve a interface web e faz proxy para Ollama

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = 3000;
const OLLAMA_URL = 'http://localhost:11434';
const GEN_PORTS = { imagem: 5000, 'vídeo': 5001 };

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
