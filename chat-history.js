/**
 * ARMAGEDON - Chat History Manager
 * Gerencia histórico de conversas com salvar/carregar/buscar/exportar
 */

class ChatHistory {
    constructor() {
        this.conversations = this.loadConversations();
        this.currentChat = null;
        this.init();
    }

    init() {
        this.createUI();
        this.attachEventListeners();
    }

    createUI() {
        // Botões de controle
        const controlsHTML = `
            <div id="chat-controls" style="display: flex; gap: 8px; margin-bottom: 15px; flex-wrap: wrap;">
                <button id="btn-new-chat" class="btn-control">💾 Novo Chat</button>
                <button id="btn-load-chat" class="btn-control">📂 Carregar</button>
                <button id="btn-search-chat" class="btn-control">🔍 Buscar</button>
                <button id="btn-export-pdf" class="btn-control">📄 PDF</button>
                <button id="btn-export-txt" class="btn-control">📝 TXT</button>
                <button id="btn-delete-chat" class="btn-control">🗑️ Deletar</button>
            </div>

            <!-- Modal de Histórico -->
            <div id="history-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 9999; padding: 20px;">
                <div style="background: #1a1a1a; border: 2px solid #ff1744; border-radius: 8px; padding: 20px; max-width: 600px; margin: auto; max-height: 80vh; overflow-y: auto;">
                    <h2 style="color: #ff1744; margin-bottom: 15px;">Histórico de Conversas</h2>
                    <input type="text" id="search-input" placeholder="Buscar conversa..." style="width: 100%; padding: 10px; background: #0a0a0a; border: 1px solid #333; color: #fff; margin-bottom: 15px; border-radius: 4px;">
                    <div id="history-list" style="display: flex; flex-direction: column; gap: 10px;"></div>
                    <button id="btn-close-modal" style="width: 100%; padding: 10px; background: #ff1744; color: #fff; border: none; border-radius: 4px; cursor: pointer; margin-top: 15px;">Fechar</button>
                </div>
            </div>
        `;

        // Inserir controles acima das mensagens
        const messagesDiv = document.querySelector('.messages');
        if (messagesDiv) {
            messagesDiv.insertAdjacentHTML('beforebegin', controlsHTML);
        }

        // Estilos
        const style = document.createElement('style');
        style.textContent = `
            .btn-control {
                padding: 8px 12px;
                background: linear-gradient(135deg, #ff1744 0%, #ff6f00 100%);
                color: white;
                border: 1px solid #ff1744;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 600;
                transition: all 0.3s;
            }
            .btn-control:hover {
                box-shadow: 0 0 15px rgba(255, 23, 68, 0.8);
            }
            .history-item {
                padding: 10px;
                background: #0a0a0a;
                border: 1px solid #333;
                border-radius: 4px;
                cursor: pointer;
                transition: all 0.2s;
            }
            .history-item:hover {
                border-color: #ff1744;
                background: #1a1a1a;
            }
        `;
        document.head.appendChild(style);
    }

    attachEventListeners() {
        document.getElementById('btn-new-chat')?.addEventListener('click', () => this.newChat());
        document.getElementById('btn-load-chat')?.addEventListener('click', () => this.showHistory());
        document.getElementById('btn-search-chat')?.addEventListener('click', () => this.showHistory());
        document.getElementById('btn-export-pdf')?.addEventListener('click', () => this.exportPDF());
        document.getElementById('btn-export-txt')?.addEventListener('click', () => this.exportTXT());
        document.getElementById('btn-delete-chat')?.addEventListener('click', () => this.deleteChat());
        document.getElementById('btn-close-modal')?.addEventListener('click', () => this.closeHistory());
        document.getElementById('search-input')?.addEventListener('input', (e) => this.searchChats(e.target.value));
    }

    saveConversation(title = null) {
        const messagesDiv = document.querySelector('.messages');
        const messages = Array.from(messagesDiv.querySelectorAll('.message'));

        const chatData = {
            id: Date.now(),
            title: title || `Chat ${new Date().toLocaleString('pt-BR')}`,
            messages: messages.map(msg => ({
                role: msg.classList.contains('user') ? 'user' : 'assistant',
                content: msg.textContent,
                timestamp: new Date().toISOString()
            })),
            createdAt: new Date().toISOString()
        };

        this.conversations.push(chatData);
        this.saveConversations();
        this.currentChat = chatData.id;

        console.log('Chat salvo:', chatData.title);
        alert(`Chat salvo: ${chatData.title}`);
    }

    loadConversation(id) {
        const chat = this.conversations.find(c => c.id === id);
        if (!chat) return;

        const messagesDiv = document.querySelector('.messages');
        messagesDiv.innerHTML = '';

        chat.messages.forEach(msg => {
            const msgEl = document.createElement('div');
            msgEl.className = `message ${msg.role === 'user' ? 'user' : 'assistant'}`;
            msgEl.innerHTML = `<div class="message-content">${msg.content}</div>`;
            messagesDiv.appendChild(msgEl);
        });

        this.currentChat = id;
        this.closeHistory();
        console.log('Chat carregado:', chat.title);
    }

    deleteChat() {
        if (!this.currentChat) {
            alert('Nenhum chat para deletar');
            return;
        }

        if (confirm('Deletar este chat?')) {
            this.conversations = this.conversations.filter(c => c.id !== this.currentChat);
            this.saveConversations();
            this.currentChat = null;
            document.querySelector('.messages').innerHTML = '';
            alert('Chat deletado');
        }
    }

    searchChats(term) {
        const listDiv = document.getElementById('history-list');
        if (!listDiv) return;

        const filtered = this.conversations.filter(c =>
            c.title.toLowerCase().includes(term.toLowerCase())
        );

        listDiv.innerHTML = filtered.map(chat => `
            <div class="history-item" onclick="chatHistory.loadConversation(${chat.id})">
                <strong>${chat.title}</strong>
                <div style="font-size: 11px; color: #999; margin-top: 5px;">
                    ${new Date(chat.createdAt).toLocaleString('pt-BR')} - ${chat.messages.length} mensagens
                </div>
            </div>
        `).join('');
    }

    showHistory() {
        const modal = document.getElementById('history-modal');
        if (modal) {
            modal.style.display = 'block';
            this.searchChats('');
        }
    }

    closeHistory() {
        const modal = document.getElementById('history-modal');
        if (modal) modal.style.display = 'none';
    }

    exportTXT() {
        const chat = this.conversations.find(c => c.id === this.currentChat);
        if (!chat) {
            alert('Nenhum chat para exportar');
            return;
        }

        let content = `=== ${chat.title} ===\n`;
        content += `Criado: ${new Date(chat.createdAt).toLocaleString('pt-BR')}\n\n`;

        chat.messages.forEach(msg => {
            content += `[${msg.role.toUpperCase()}]\n${msg.content}\n\n`;
        });

        const blob = new Blob([content], { type: 'text/plain; charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat_${chat.id}.txt`;
        a.click();
    }

    exportPDF() {
        const chat = this.conversations.find(c => c.id === this.currentChat);
        if (!chat) {
            alert('Nenhum chat para exportar');
            return;
        }

        let html = `<h1>${chat.title}</h1>`;
        html += `<p>Criado: ${new Date(chat.createdAt).toLocaleString('pt-BR')}</p>`;
        html += `<hr>`;

        chat.messages.forEach(msg => {
            html += `<p><strong>[${msg.role.toUpperCase()}]</strong></p>`;
            html += `<p>${msg.content}</p>`;
            html += `<hr>`;
        });

        const printWindow = window.open('', '_blank');
        printWindow.document.write(`
            <html>
            <head>
                <title>${chat.title}</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; }
                    strong { color: #ff1744; }
                </style>
            </head>
            <body>${html}</body>
            </html>
        `);
        printWindow.document.close();
        printWindow.print();
    }

    newChat() {
        const title = prompt('Nome do novo chat:');
        if (title) {
            this.saveConversation(title);
            document.querySelector('.messages').innerHTML = '';
        }
    }

    loadConversations() {
        try {
            return JSON.parse(localStorage.getItem('armagedon_chats')) || [];
        } catch {
            return [];
        }
    }

    saveConversations() {
        localStorage.setItem('armagedon_chats', JSON.stringify(this.conversations));
    }
}

// Inicializar quando página carregar
const chatHistory = new ChatHistory();
