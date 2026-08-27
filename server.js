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
