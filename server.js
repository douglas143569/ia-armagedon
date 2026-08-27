// ARMAGEDON - Hub Server
// Serve a interface web e faz proxy para Ollama

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = 3000;
const OLLAMA_URL = 'http://localhost:11434';

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
