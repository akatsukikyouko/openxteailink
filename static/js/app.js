class BookTransferApp {
    constructor() {
        this.selectedFiles = [];
        this.convertResolve = null;
        this.initializeElements();
        this.bindEvents();
        this.loadSettings();
        this.refreshQueue();
        this.checkDeviceConnection();

        // 定期检查设备连接状态（每30秒）
        setInterval(() => this.checkDeviceConnection(), 30000);

        // 定期刷新队列（每5秒）
        setInterval(() => this.refreshQueue(), 5000);
    }

    initializeElements() {
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.folderInput = document.getElementById('folderInput');
        this.fileList = document.getElementById('fileList');
        this.settingsForm = document.getElementById('settingsForm');
        this.deviceIp = document.getElementById('deviceIp');
        this.devicePort = document.getElementById('devicePort');
        this.deviceStatusBadge = document.getElementById('deviceStatusBadge');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.queueList = document.getElementById('queueList');
        this.uploadProgress = document.getElementById('uploadProgress');
        this.progressFill = document.getElementById('progressFill');
        this.toastContainer = document.getElementById('toastContainer');
        this.convertModal = document.getElementById('convertModal');
        this.convertableCount = document.getElementById('convertableCount');
        this.convertableList = document.getElementById('convertableList');
        this.chatToggle = document.getElementById('chatToggle');
    }

    bindEvents() {
        // 禁用上传区域的点击事件 - 只能通过按钮选择
        // this.uploadArea.addEventListener('click', (e) => {
        //     // 如果点击的是按钮，不触发文件选择
        //     if (e.target.closest('button')) return;
        //     this.fileInput.click();
        // });

        // 文件选择按钮
        document.getElementById('selectFileBtn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.fileInput.click();
        });

        // 文件夹选择按钮
        document.getElementById('selectFolderBtn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.folderInput.click();
        });

        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e.target.files));
        this.folderInput.addEventListener('change', (e) => this.handleFileSelect(e.target.files));

        // 拖拽事件
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadArea.classList.add('dragover');
        });

        this.uploadArea.addEventListener('dragleave', () => {
            this.uploadArea.classList.remove('dragover');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('dragover');
            this.handleFileSelect(e.dataTransfer.files);
        });

        // 设置表单事件
        this.settingsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveSettings();
        });

        document.getElementById('refreshQueue').addEventListener('click', () => {
            this.refreshQueue();
        });

        document.getElementById('clearQueue').addEventListener('click', () => {
            this.clearQueue();
        });

        // 转换对话框事件
        document.getElementById('modalConvert').addEventListener('click', () => {
            this.hideConvertModal(true);
        });

        document.getElementById('modalNoConvert').addEventListener('click', () => {
            this.hideConvertModal(false);
        });

        // 格式选择事件
        document.querySelectorAll('input[name="convertFormat"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.updateFormatLabelStyles();
            });
        });
    }

    async handleFileSelect(files) {
        if (files.length === 0) return;

        // 清空之前的文件列表，只处理当前批次
        this.selectedFiles = [];
        this.convertResolve = null;

        // 将当前批次的文件添加到选择列表
        for (let file of files) {
            this.selectedFiles.push(file);
        }

        // 显示文件列表
        this.displaySelectedFiles();

        // 检查当前批次是否有可转换的文件
        const convertableFiles = this.selectedFiles.filter(file => {
            const ext = file.name.split('.').pop().toLowerCase();
            return ['epub', 'mobi', 'pdf', 'png'].includes(ext);
        });

        if (convertableFiles.length > 0) {
            // 显示转换确认对话框
            const shouldConvert = await this.showConvertModal(convertableFiles);
            await this.uploadFiles(shouldConvert);
        } else {
            // 直接上传
            await this.uploadFiles(false);
        }

        // 上传完成后清空文件列表
        this.selectedFiles = [];
        this.fileList.classList.remove('show');
    }

    displaySelectedFiles() {
        this.fileList.innerHTML = '';
        this.fileList.classList.add('show');

        this.selectedFiles.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'file-item';
            item.innerHTML = `
                <div class="file-item-name">${file.name}</div>
                <div class="file-item-size">${this.formatFileSize(file.size)}</div>
                <button class="btn btn-small btn-danger" onclick="app.removeFile(${index})">删除</button>
            `;
            this.fileList.appendChild(item);
        });
    }

    removeFile(index) {
        this.selectedFiles.splice(index, 1);
        this.displaySelectedFiles();

        if (this.selectedFiles.length === 0) {
            this.fileList.classList.remove('show');
        }
    }

    showConvertModal(convertableFiles) {
        return new Promise((resolve) => {
            this.convertResolve = resolve;

            // 设置对话框内容
            this.convertableCount.textContent = convertableFiles.length;
            this.convertableList.innerHTML = convertableFiles.map(file =>
                `<div style="padding: 4px 0; font-size: 13px; color: var(--text-secondary);">• ${file.name}</div>`
            ).join('');

            // 检查是否包含EPUB或MOBI文件（用于智能混合模式）
            const hasEpubOrMobi = convertableFiles.some(file => {
                const ext = file.name.split('.').pop().toLowerCase();
                return ['epub', 'mobi'].includes(ext);
            });

            // 显示/隐藏智能混合选项
            const autoLabel = document.getElementById('formatAutoLabel');
            if (hasEpubOrMobi) {
                autoLabel.style.display = 'flex';
            } else {
                autoLabel.style.display = 'none';
            }

            // 重置格式选择为默认XTG
            document.querySelector('input[name="convertFormat"][value="xtg"]').checked = true;
            this.updateFormatLabelStyles();

            // 显示对话框
            this.convertModal.classList.add('show');
        });
    }

    updateFormatLabelStyles() {
        const xtgLabel = document.getElementById('formatXtgLabel');
        const xthLabel = document.getElementById('formatXthLabel');
        const autoLabel = document.getElementById('formatAutoLabel');
        const selectedFormat = document.querySelector('input[name="convertFormat"]:checked').value;

        // 重置所有标签样式
        [xtgLabel, xthLabel, autoLabel].forEach(label => {
            if (label) {
                label.style.borderColor = 'var(--border-color)';
                label.style.backgroundColor = 'transparent';
                label.style.color = 'var(--text-primary)';
            }
        });

        // 设置选中标签的样式
        let selectedLabel;
        if (selectedFormat === 'xtg') {
            selectedLabel = xtgLabel;
        } else if (selectedFormat === 'xth') {
            selectedLabel = xthLabel;
        } else if (selectedFormat === 'auto') {
            selectedLabel = autoLabel;
        }

        if (selectedLabel) {
            selectedLabel.style.borderColor = 'var(--primary-color)';
            selectedLabel.style.backgroundColor = 'var(--primary-color)';
            selectedLabel.style.color = 'white';
        }
    }

    hideConvertModal(shouldConvert) {
        // 保存选择的格式
        const selectedFormat = document.querySelector('input[name="convertFormat"]:checked').value;
        this.selectedFormat = selectedFormat;

        this.convertModal.classList.remove('show');

        // 解析Promise
        if (this.convertResolve) {
            this.convertResolve(shouldConvert);
            this.convertResolve = null;
        }
    }

    async uploadFiles(convertToXtc) {
        let successCount = 0;
        let failCount = 0;

        for (let i = 0; i < this.selectedFiles.length; i++) {
            const file = this.selectedFiles[i];
            const fileExt = file.name.split('.').pop().toLowerCase();

            // 判断是否需要转换
            const shouldConvertThis = convertToXtc && ['epub', 'mobi', 'pdf', 'png'].includes(fileExt);

            try {
                this.showUploadProgress((i / this.selectedFiles.length) * 100);
                await this.uploadFile(file, shouldConvertThis);
                successCount++;
            } catch (error) {
                failCount++;
                this.showToast(`上传 ${file.name} 失败: ${error.message}`, 'error');
            }
        }

        this.hideUploadProgress();

        // 清空文件列表
        this.selectedFiles = [];
        this.fileList.classList.remove('show');

        // 显示结果
        if (successCount > 0) {
            this.showToast(`成功上传 ${successCount} 个文件`, 'success');
        }
        if (failCount > 0) {
            this.showToast(`${failCount} 个文件上传失败`, 'error');
        }

        // 自动刷新队列
        this.refreshQueue();
    }

    async uploadFile(file, convertToXtc = false) {
        const formData = new FormData();
        formData.append('file', file);

        // 添加转换标志和格式
        if (convertToXtc) {
            formData.append('convert_to_xtc', 'true');
            // 添加选择的格式（xtg或xth）
            if (this.selectedFormat) {
                formData.append('format', this.selectedFormat);
            }
        }

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.message || '上传失败');
            }

            return result;
        } catch (error) {
            throw error;
        }
    }

    showUploadProgress(percent) {
        this.uploadProgress.style.display = 'block';
        this.progressFill.style.width = percent + '%';
    }

    hideUploadProgress() {
        this.uploadProgress.style.display = 'none';
        this.progressFill.style.width = '0%';
    }

    async refreshQueue() {
        try {
            const response = await fetch('/api/queue');
            const queue = await response.json();

            // 过滤掉已完成的文件（只保留未完成的）
            const activeQueue = queue.filter(item =>
                item.status !== 'completed' && item.status !== 'missing'
            );

            this.renderQueue(activeQueue);
        } catch (error) {
            console.error('获取队列失败:', error);
        }
    }

    renderQueue(queue) {
        this.queueList.innerHTML = '';

        if (queue.length === 0) {
            this.queueList.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 5v14H5V5h14m0-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-4.86 8.86l-3 3.87L9 13.14 6 17h12l-3.86-5.14z"/>
                    </svg>
                    <p>队列为空</p>
                </div>
            `;
            return;
        }

        queue.forEach(item => {
            const queueItem = document.createElement('div');
            queueItem.className = 'queue-item';

            const statusIcon = this.getStatusIcon(item.status);
            const statusText = this.getStatusText(item.status);

            // 检查是否是XTC文件
            const isXTC = item.name.toLowerCase().endsWith('.xtc');
            const viewButton = isXTC ? `
                <button class="btn btn-small btn-primary" onclick="app.viewXTCFile('${item.id}', '${item.name}')" title="浏览XTC文件">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/>
                    </svg>
                    浏览
                </button>
            ` : '';

            queueItem.innerHTML = `
                <div class="queue-item-info">
                    <div class="queue-item-name">${item.name}</div>
                    <div class="queue-item-meta">
                        <span>${this.formatFileSize(item.size)}</span>
                        <span class="queue-item-status">
                            ${statusIcon}
                            ${statusText}
                        </span>
                        <span>${new Date(item.upload_time).toLocaleString()}</span>
                    </div>
                </div>
                <div class="queue-item-actions">
                    ${viewButton}
                    <button class="btn btn-small btn-danger" onclick="app.removeFromQueue('${item.id}')">删除</button>
                </div>
            `;
            this.queueList.appendChild(queueItem);
        });
    }

    viewXTCFile(fileId, fileName) {
        // 打开XTC查看器 - 直接使用文件ID（更安全）
        if (fileId) {
            const viewerUrl = `/xtc-viewer?id=${encodeURIComponent(fileId)}`;
            window.open(viewerUrl, '_blank');
        } else {
            this.showToast('文件ID不存在');
        }
    }

    getStatusIcon(status) {
        const icons = {
            'pending': '⏳',
            'transferring': '📤',
            'completed': '✅',
            'failed': '❌',
            'missing': '⚠️'
        };
        return icons[status] || '📄';
    }

    getStatusText(status) {
        const statusMap = {
            'pending': '等待传输',
            'transferring': '传输中',
            'completed': '已完成',
            'failed': '传输失败',
            'missing': '文件丢失'
        };
        return statusMap[status] || status;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async removeFromQueue(itemId) {
        try {
            const response = await fetch(`/api/queue/${itemId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                this.showToast('已从队列中删除', 'success');
                this.refreshQueue();
            } else {
                this.showToast('删除失败', 'error');
            }
        } catch (error) {
            this.showToast('删除失败', 'error');
        }
    }

    async clearQueue() {
        if (!confirm('确定要清空整个队列吗?')) return;

        try {
            const response = await fetch('/api/queue', {
                method: 'DELETE'
            });

            if (response.ok) {
                this.showToast('队列已清空', 'success');
                this.refreshQueue();
            } else {
                this.showToast('清空队列失败', 'error');
            }
        } catch (error) {
            this.showToast('清空队列失败', 'error');
        }
    }

    async saveSettings() {
        const settings = {
            ip: this.deviceIp.value,
            port: parseInt(this.devicePort.value)
        };

        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (response.ok) {
                this.showToast('设置已保存', 'success');
                this.checkDeviceConnection();
            } else {
                this.showToast('保存设置失败', 'error');
            }
        } catch (error) {
            this.showToast('保存设置失败', 'error');
        }
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/settings');
            const settings = await response.json();

            this.deviceIp.value = settings.ip || '192.168.68.245';
            this.devicePort.value = settings.port || 80;
        } catch (error) {
            console.error('加载设置失败:', error);
        }
    }

    async checkDeviceConnection() {
        // 设置默认状态为离线
        this.deviceStatusBadge.className = 'status-badge offline';
        this.statusText.textContent = '未连接';

        try {
            const response = await fetch('/api/device/status');

            if (!response.ok) {
                throw new Error('连接检查失败');
            }

            const result = await response.json();

            if (result.connected) {
                this.deviceStatusBadge.className = 'status-badge online';
                this.statusText.textContent = '检测到设备已连接';
            } else {
                this.statusText.textContent = '未连接';
            }
        } catch (error) {
            console.error('设备连接检查失败:', error);
            this.statusText.textContent = '未连接';
        }
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            'success': '<svg class="toast-icon" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>',
            'error': '<svg class="toast-icon" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>',
            'info': '<svg class="toast-icon" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>'
        };

        toast.innerHTML = `
            ${icons[type] || icons.info}
            <div class="toast-message">${message}</div>
        `;

        this.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// 初始化应用
const app = new BookTransferApp();
