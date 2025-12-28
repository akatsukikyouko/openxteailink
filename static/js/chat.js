class ChatWindow {
    constructor() {
        this.isOpen = false;
        this.config = null;
        this.conversationHistory = [];
        this.isTyping = false;

        this.initializeElements();
        this.bindEvents();
        this.loadConfig();
    }

    initializeElements() {
        this.chatToggle = document.getElementById('chatToggle');
        this.chatWindow = document.getElementById('chatWindow');
        this.closeChat = document.getElementById('closeChat');
        this.chatSettings = document.getElementById('chatSettings');
        this.chatMessages = document.getElementById('chatMessages');
        this.chatInput = document.getElementById('chatInput');
        this.sendMessage = document.getElementById('sendMessage');
        this.aiSettingsModal = document.getElementById('aiSettingsModal');
        this.aiSettingsForm = document.getElementById('aiSettingsForm');
    }

    bindEvents() {
        // 打开/关闭聊天窗口
        this.chatToggle.addEventListener('click', () => this.toggleChat());
        this.closeChat.addEventListener('click', () => this.closeChatWindow());

        // 打开设置
        this.chatSettings.addEventListener('click', () => this.openSettings());

        // 发送消息
        this.sendMessage.addEventListener('click', () => this.handleSend());
        this.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSend();
            }
        });

        // 自动调整输入框高度
        this.chatInput.addEventListener('input', () => {
            this.chatInput.style.height = 'auto';
            this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 120) + 'px';
        });

        // 设置表单
        this.aiSettingsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveSettings();
        });

        document.getElementById('cancelAiSettings').addEventListener('click', () => {
            this.aiSettingsModal.classList.remove('show');
        });

        document.getElementById('testAiConnection').addEventListener('click', () => {
            this.testConnection();
        });

        document.getElementById('addMcpServer').addEventListener('click', () => {
            this.addMcpServerField();
        });

        // 保存按钮点击事件
        document.getElementById('saveAiSettings').addEventListener('click', () => {
            console.log('保存按钮被点击');
            this.saveSettings();
        });
    }

    toggleChat() {
        if (this.isOpen) {
            this.closeChatWindow();
        } else {
            this.openChat();
        }
    }

    openChat() {
        this.chatWindow.classList.add('show');
        this.chatToggle.style.display = 'none';
        this.isOpen = true;
        this.chatInput.focus();
    }

    closeChatWindow() {
        this.chatWindow.classList.remove('show');
        this.chatToggle.style.display = 'flex';
        this.isOpen = false;
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/chat/config');
            this.config = await response.json();
        } catch (error) {
            console.error('加载AI配置失败:', error);
            this.config = {};
        }
    }

    openSettings() {
        // 填充当前配置
        document.getElementById('aiEnabled').value = this.config.enabled ? 'true' : 'false';

        if (this.config.openai) {
            document.getElementById('openaiBaseUrl').value = this.config.openai.base_url || '';
            // 使用隐藏的真实key,如果不存在则使用当前的
            const apiKey = this.config.openai._api_key_hidden || this.config.openai.api_key || '';
            document.getElementById('openaiApiKey').value = apiKey;
            document.getElementById('openaiModel').value = this.config.openai.model || '';
        }

        // 填充MCP服务器列表
        const mcpList = document.getElementById('mcpServersList');
        mcpList.innerHTML = '';

        if (this.config.mcp_servers && this.config.mcp_servers.length > 0) {
            this.config.mcp_servers.forEach((server, index) => {
                // 使用隐藏的真实custom_header
                const serverConfig = {
                    ...server,
                    custom_header: server._custom_header_hidden || server.custom_header || ''
                };
                this.addMcpServerField(serverConfig);
            });
        } else {
            this.addMcpServerField();
        }

        // 生图设置 - 根据选择的提供商填充配置
        const provider = this.config.default_image_provider || 'disabled';

        // 设置生图选项下拉框
        document.getElementById('imageProvider').value = provider;

        // 根据提供商填充对应的配置
        if (provider === 'zimage' && this.config.image_generation) {
            // 使用模搭配置
            document.getElementById('imageModelId').value =
                this.config.image_generation.model_id || 'Tongyi-MAI/Z-Image-Turbo';
            document.getElementById('imageApiKey').value =
                this.config.image_generation._api_key_hidden || this.config.image_generation.api_key || '';
        } else if (provider === 'doubao' && this.config.doubao_image) {
            // 使用豆包配置
            document.getElementById('imageModelId').value =
                this.config.doubao_image.model_id || 'doubao-seedream-4-5-251128';
            document.getElementById('imageApiKey').value =
                this.config.doubao_image._api_key_hidden || this.config.doubao_image.api_key || '';
        } else {
            // 关闭状态，清空或显示默认
            document.getElementById('imageModelId').value = '';
            document.getElementById('imageApiKey').value = '';
        }

        this.aiSettingsModal.classList.add('show');
    }

    addMcpServerField(server = null) {
        const mcpList = document.getElementById('mcpServersList');
        const index = mcpList.children.length;

        const div = document.createElement('div');
        div.className = 'mcp-server-item';
        div.style.cssText = 'margin-bottom: 12px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid var(--border-color);';
        div.innerHTML = `
            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                <input type="text" class="form-input mcp-name" placeholder="服务器名称"
                    value="${server ? server.name : ''}" style="flex: 1;">
                <button type="button" class="btn btn-small btn-danger remove-mcp" style="padding: 6px 12px;">删除</button>
            </div>
            <input type="text" class="form-input mcp-url" placeholder="服务器URL"
                value="${server ? server.url : ''}" style="margin-bottom: 8px;">
            <div style="margin-bottom: 8px;">
                <label style="display: flex; align-items: center; font-size: 12px; color: var(--text-secondary);">
                    <input type="checkbox" class="mcp-has-header" ${server && server.has_header ? 'checked' : ''} style="margin-right: 4px;">
                    需要Header (勾选后下方会出现输入框)
                </label>
            </div>
            <div class="mcp-custom-header-container" style="margin-bottom: 8px; display: none;">
                <input type="text" class="form-input mcp-custom-header" placeholder="自定义Header - 例: Authorization: bearer xxx"
                    value="${server ? (server._custom_header_hidden || server.custom_header || '') : ''}">
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
                    支持格式: "Authorization: bearer xxx" 或 JSON: {"Authorization": "bearer xxx"}
                </div>
            </div>
            <div style="margin-top: 8px;">
                <label style="font-size: 12px; color: var(--text-secondary);">
                    <input type="checkbox" class="mcp-enabled" ${server && server.enabled ? 'checked' : ''}>
                    启用此服务器
                </label>
            </div>
        `;

        // 绑定删除事件
        div.querySelector('.remove-mcp').addEventListener('click', () => {
            div.remove();
        });

        // 绑定"需要Header"复选框事件
        div.querySelector('.mcp-has-header').addEventListener('change', (e) => {
            const customHeaderDiv = div.querySelector('.mcp-custom-header-container');
            customHeaderDiv.style.display = e.target.checked ? 'block' : 'none';
        });

        // 如果默认勾选了"需要Header",显示自定义Header输入框
        if (server && server.has_header) {
            div.querySelector('.mcp-custom-header-container').style.display = 'block';
        }

        mcpList.appendChild(div);
    }

    async saveSettings() {
        console.log('开始保存AI配置...');

        // 获取生图配置
        const provider = document.getElementById('imageProvider').value;
        const modelId = document.getElementById('imageModelId').value;
        const apiKey = document.getElementById('imageApiKey').value;

        // 根据选择的提供商构建配置
        let config = {
            enabled: document.getElementById('aiEnabled').value === 'true',
            openai: {
                base_url: document.getElementById('openaiBaseUrl').value,
                api_key: document.getElementById('openaiApiKey').value,
                model: document.getElementById('openaiModel').value
            },
            mcp_servers: [],
            default_image_provider: provider
        };

        // 根据提供商设置对应的配置，URL锁定
        if (provider === 'zimage') {
            // 使用模搭
            config.image_generation = {
                enabled: true,
                tool: 'internal',
                api_key: apiKey,
                base_url: 'https://api-inference.modelscope.cn/',  // 锁定URL
                model_id: modelId
            };
        } else if (provider === 'doubao') {
            // 使用豆包
            config.doubao_image = {
                enabled: true,
                api_key: apiKey,
                base_url: 'https://ark.cn-beijing.volces.com/api/v3',  // 锁定URL
                model_id: modelId
            };
            // 保持image_generation的默认配置
            config.image_generation = this.config.image_generation || {
                enabled: false,
                tool: 'internal',
                api_key: '',
                base_url: 'https://api-inference.modelscope.cn/',
                model_id: 'Tongyi-MAI/Z-Image-Turbo'
            };
        } else {
            // 关闭生图
            config.image_generation = {
                enabled: false,
                tool: 'internal',
                api_key: '',
                base_url: 'https://api-inference.modelscope.cn/',
                model_id: 'Tongyi-MAI/Z-Image-Turbo'
            };
            config.doubao_image = {
                enabled: false,
                api_key: '',
                base_url: 'https://ark.cn-beijing.volces.com/api/v3',
                model_id: 'doubao-seedream-4-5-251128'
            };
        }

        console.log('基础配置:', {
            enabled: config.enabled,
            has_openai: !!config.openai.base_url,
            has_image_gen: !!config.image_generation.base_url
        });

        // 收集MCP服务器配置
        document.querySelectorAll('.mcp-server-item').forEach((item, index) => {
            const name = item.querySelector('.mcp-name').value;
            const url = item.querySelector('.mcp-url').value;
            const hasHeaderCheckbox = item.querySelector('.mcp-has-header');
            const custom_header = item.querySelector('.mcp-custom-header')?.value || '';
            const enabled = item.querySelector('.mcp-enabled').checked;

            console.log(`MCP服务器 ${index + 1}:`, { name, url, has_header: hasHeaderCheckbox.checked, custom_header_len: custom_header.length });

            // 只收集name和url都不为空的服务器
            if (name && url) {
                const serverConfig = {
                    name,
                    url,
                    enabled,
                    has_header: hasHeaderCheckbox.checked,
                    custom_header: hasHeaderCheckbox.checked ? custom_header : ''
                };
                config.mcp_servers.push(serverConfig);
            }
        });

        console.log(`总共收集了 ${config.mcp_servers.length} 个MCP服务器`);
        console.log('准备发送配置到服务器...');

        try {
            console.log('发送POST请求到 /api/chat/config');
            const response = await fetch('/api/chat/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            console.log('收到响应，状态码:', response.status);
            const result = await response.json();
            console.log('响应内容:', result);

            if (result.success) {
                console.log('保存成功');
                this.showToast('AI配置已保存', 'success');
                this.config = config;
                this.aiSettingsModal.classList.remove('show');
                // 重新加载配置以获取最新状态
                await this.loadConfig();
            } else {
                console.error('保存失败:', result.message);
                this.showToast(result.message || '保存失败', 'error');
            }
        } catch (error) {
            console.error('保存配置失败:', error);
            this.showToast('保存配置失败: ' + error.message, 'error');
        }
    }

    async testConnection() {
        const btn = document.getElementById('testAiConnection');
        const originalText = btn.textContent;
        btn.textContent = '测试中...';
        btn.disabled = true;

        try {
            const response = await fetch('/api/chat/test');
            const result = await response.json();

            if (result.pydantic_available && result.agent_initialized) {
                this.showToast('AI服务连接成功!', 'success');
            } else {
                this.showToast('AI服务未正确配置', 'error');
            }
        } catch (error) {
            this.showToast('测试连接失败', 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }

    async handleSend() {
        const message = this.chatInput.value.trim();

        if (!message || this.isTyping) return;

        // 添加用户消息
        this.addMessage('user', message);
        this.chatInput.value = '';
        this.chatInput.style.height = 'auto';

        // 保存到历史
        this.conversationHistory.push({ role: 'user', content: message });

        // 显示加载状态
        this.isTyping = true;
        const loadingMessage = this.addMessage('assistant', '<div class="typing-indicator"><span></span><span></span><span></span></div>', true);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    history: this.conversationHistory
                })
            });

            const result = await response.json();

            // 移除加载消息
            loadingMessage.remove();

            if (result.success) {
                // 添加AI回复（包含图片）
                this.addMessage('assistant', result.message, false, result.images);
                this.conversationHistory.push({ role: 'assistant', content: result.message });
            } else {
                this.addMessage('assistant', '抱歉,' + (result.message || '处理失败'));
            }

        } catch (error) {
            loadingMessage.remove();
            this.addMessage('assistant', '抱歉,网络连接失败');
        } finally {
            this.isTyping = false;
        }
    }

    addMessage(role, content, isLoading = false, images = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        if (isLoading) {
            contentDiv.className += ' loading';
        }

        // 如果是assistant消息，尝试渲染markdown
        if (role === 'assistant' && !isLoading) {
            try {
                // 检查是否包含markdown语法
                if (typeof marked !== 'undefined' && (
                    content.includes('**') ||
                    content.includes('#') ||
                    content.includes('```') ||
                    content.includes('- ') ||
                    content.match(/^\d+\./m)
                )) {
                    // 配置marked选项
                    marked.setOptions({
                        breaks: true,  // 支持回车换行
                        gfm: true,      // GitHub Flavored Markdown
                        sanitize: false // 允许HTML（谨慎使用）
                    });
                    contentDiv.innerHTML = marked.parse(content);
                } else {
                    contentDiv.innerHTML = content;
                }
            } catch (e) {
                // 如果marked解析失败，使用原始内容
                contentDiv.innerHTML = content;
            }
        } else {
            contentDiv.innerHTML = content;
        }

        messageDiv.appendChild(contentDiv);

        // 如果有图片，作为独立的消息块添加
        if (images && images.length > 0) {
            images.forEach((img, index) => {
                const imageMessageDiv = document.createElement('div');
                imageMessageDiv.className = `chat-message assistant`;

                const imageContentDiv = document.createElement('div');
                imageContentDiv.className = 'message-content image-card';
                imageContentDiv.innerHTML = `
                    <div class="image-card-header">生成图片 ${index + 1}</div>
                    <div class="image-card-body">
                        <img src="${img.path}" alt="${img.name}" class="generated-image">
                    </div>
                    <div class="image-card-footer">
                        <span class="image-filename">${img.name}</span>
                    </div>
                `;

                // 点击图片在模态框中查看
                const imgElement = imageContentDiv.querySelector('.generated-image');
                imgElement.onclick = () => this.showImageModal(img.path, img.name);

                imageMessageDiv.appendChild(imageContentDiv);
                this.chatMessages.appendChild(imageMessageDiv);
            });
        }

        this.chatMessages.appendChild(messageDiv);

        // 滚动到底部
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;

        return messageDiv;
    }

    showImageModal(imageSrc, imageName) {
        // 创建模态框
        const modal = document.createElement('div');
        modal.className = 'image-modal-overlay';
        modal.innerHTML = `
            <div class="image-modal">
                <button class="image-modal-close">×</button>
                <img src="${imageSrc}" alt="${imageName}">
                <div class="image-modal-caption">${imageName}</div>
            </div>
        `;

        // 点击关闭按钮或背景关闭模态框
        modal.querySelector('.image-modal-close').onclick = () => modal.remove();
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };

        // ESC键关闭
        const escapeHandler = (e) => {
            if (e.key === 'Escape') {
                modal.remove();
                document.removeEventListener('keydown', escapeHandler);
            }
        };
        document.addEventListener('keydown', escapeHandler);

        document.body.appendChild(modal);
        setTimeout(() => modal.classList.add('show'), 10);
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.style.cssText = 'position: fixed; bottom: 100px; right: 24px; z-index: 3000;';

        const icons = {
            'success': '✓',
            'error': '✕',
            'info': 'ℹ'
        };

        toast.innerHTML = `
            <div style="width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; background: ${type === 'success' ? '#64ff64' : type === 'error' ? '#ff6464' : '#fff'}; border-radius: 50%; color: #000;">${icons[type]}</div>
            <div style="flex: 1;">${message}</div>
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// 添加聊天窗口CSS
const chatStyles = document.createElement('style');
chatStyles.textContent = `
    .chat-window {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 400px;
        height: 600px;
        max-height: calc(100vh - 48px);
        background: var(--bg-card);
        backdrop-filter: blur(20px);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        display: none;
        flex-direction: column;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        z-index: 1000;
        transition: all 0.3s ease;
    }

    .chat-window.show {
        display: flex;
        animation: slideUp 0.3s ease;
    }

    @keyframes slideUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .chat-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 20px;
        border-bottom: 1px solid var(--border-color);
        background: rgba(255, 255, 255, 0.05);
        border-radius: 16px 16px 0 0;
    }

    .chat-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
        font-size: 16px;
        color: var(--text-primary);
    }

    .chat-actions {
        display: flex;
        gap: 8px;
    }

    .chat-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .chat-message {
        display: flex;
        gap: 8px;
        animation: messageSlide 0.3s ease;
    }

    @keyframes messageSlide {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .chat-message.user {
        flex-direction: row-reverse;
    }

    .chat-message.user .message-content {
        background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.1) 100%);
        border-radius: 12px 12px 0 12px;
    }

    .chat-message.assistant .message-content {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid var(--border-color);
        border-radius: 12px 12px 12px 0;
    }

    .message-content {
        max-width: 80%;
        padding: 12px 16px;
        font-size: 14px;
        line-height: 1.5;
        color: var(--text-primary);
        word-wrap: break-word;
    }

    .message-content.loading {
        opacity: 0.7;
    }

    /* Markdown样式 */
    .message-content h1, .message-content h2, .message-content h3,
    .message-content h4, .message-content h5, .message-content h6 {
        margin-top: 12px;
        margin-bottom: 8px;
        font-weight: 600;
        line-height: 1.3;
    }

    .message-content h1 { font-size: 1.5em; }
    .message-content h2 { font-size: 1.3em; }
    .message-content h3 { font-size: 1.15em; }

    .message-content p {
        margin: 8px 0;
    }

    .message-content ul, .message-content ol {
        margin: 8px 0;
        padding-left: 24px;
    }

    .message-content li {
        margin: 4px 0;
    }

    .message-content code {
        background: rgba(0, 0, 0, 0.3);
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 0.9em;
    }

    .message-content pre {
        background: rgba(0, 0, 0, 0.3);
        padding: 12px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 8px 0;
    }

    .message-content pre code {
        background: none;
        padding: 0;
    }

    .message-content blockquote {
        border-left: 3px solid rgba(255, 255, 255, 0.3);
        padding-left: 12px;
        margin: 8px 0;
        color: var(--text-secondary);
        font-style: italic;
    }

    .message-content a {
        color: #64b4ff;
        text-decoration: underline;
    }

    .message-content table {
        border-collapse: collapse;
        width: 100%;
        margin: 8px 0;
    }

    .message-content th, .message-content td {
        border: 1px solid var(--border-color);
        padding: 8px;
        text-align: left;
    }

    .message-content th {
        background: rgba(255, 255, 255, 0.1);
        font-weight: 600;
    }

    .message-content img {
        max-width: 100%;
        border-radius: 8px;
        margin: 8px 0;
    }

    /* 图片卡片样式 */
    .message-content.image-card {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 0;
        overflow: hidden;
        max-width: 100%;
    }

    .image-card-header {
        background: rgba(255, 255, 255, 0.1);
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 600;
        color: var(--text-secondary);
        border-bottom: 1px solid var(--border-color);
    }

    .image-card-body {
        padding: 12px;
        text-align: center;
        background: rgba(0, 0, 0, 0.2);
    }

    .generated-image {
        max-width: 100%;
        max-height: 300px;
        border-radius: 8px;
        cursor: pointer;
        transition: transform 0.2s ease;
        object-fit: contain;
    }

    .generated-image:hover {
        transform: scale(1.02);
    }

    .image-card-footer {
        padding: 8px 12px;
        font-size: 11px;
        color: var(--text-muted);
        border-top: 1px solid var(--border-color);
        background: rgba(255, 255, 255, 0.05);
    }

    .image-filename {
        font-family: 'Consolas', 'Monaco', monospace;
    }

    /* 图片模态框样式 */
    .image-modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        backdrop-filter: blur(10px);
        z-index: 10000;
        display: flex;
        justify-content: center;
        align-items: center;
        opacity: 0;
        transition: opacity 0.3s ease;
    }

    .image-modal-overlay.show {
        opacity: 1;
    }

    .image-modal {
        position: relative;
        max-width: 90vw;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    .image-modal img {
        max-width: 100%;
        max-height: 80vh;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    }

    .image-modal-close {
        position: absolute;
        top: -40px;
        right: 0;
        width: 32px;
        height: 32px;
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.3);
        border-radius: 50%;
        color: #fff;
        font-size: 20px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
    }

    .image-modal-close:hover {
        background: rgba(255, 255, 255, 0.2);
        transform: scale(1.1);
    }

    .image-modal-caption {
        margin-top: 16px;
        color: var(--text-secondary);
        font-size: 14px;
        text-align: center;
    }

    .message-content hr {
        border: none;
        border-top: 1px solid var(--border-color);
        margin: 12px 0;
    }

    .typing-indicator {
        display: flex;
        gap: 4px;
        padding: 8px 0;
    }

    .typing-indicator span {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--text-muted);
        animation: typing 1.4s ease-in-out infinite;
    }

    .typing-indicator span:nth-child(2) {
        animation-delay: 0.2s;
    }

    .typing-indicator span:nth-child(3) {
        animation-delay: 0.4s;
    }

    @keyframes typing {
        0%, 60%, 100% { transform: translateY(0); }
        30% { transform: translateY(-8px); }
    }

    .chat-input-area {
        display: flex;
        gap: 12px;
        padding: 16px;
        border-top: 1px solid var(--border-color);
        background: rgba(255, 255, 255, 0.02);
        border-radius: 0 0 16px 16px;
    }

    .chat-input {
        flex: 1;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 10px 14px;
        color: var(--text-primary);
        font-size: 14px;
        font-family: inherit;
        resize: none;
        outline: none;
        transition: all 0.2s ease;
        max-height: 120px;
        overflow-y: auto;
    }

    .chat-input:focus {
        border-color: rgba(255, 255, 255, 0.3);
        background: rgba(255, 255, 255, 0.08);
    }

    .chat-input::placeholder {
        color: var(--text-muted);
    }

    .send-button {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, #fff 0%, rgba(255,255,255,0.9) 100%);
        border: none;
        border-radius: 8px;
        color: var(--bg-dark);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
        flex-shrink: 0;
    }

    .send-button:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(255, 255, 255, 0.3);
    }

    .send-button:active {
        transform: scale(0.95);
    }

    @media (max-width: 480px) {
        .chat-window {
            width: calc(100vw - 24px);
            height: calc(100vh - 100px);
            bottom: 12px;
            right: 12px;
        }
    }
`;
document.head.appendChild(chatStyles);

// 初始化聊天窗口
const chatWindow = new ChatWindow();
