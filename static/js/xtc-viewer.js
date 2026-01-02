/**
 * XTC文件浏览器
 * 支持XTC（容器）、XTG（1位单色）和XTH（4级灰度）格式
 * 基于 tool/XtcViewer-main 的实现
 */

class XTGH_Image {
    // XTG/XTH 单页图像
    constructor(arrayBuffer) {
        this.buf = arrayBuffer;
        this.dv = new DataView(arrayBuffer);
        this.header = null;
        this.parseHeader();
    }

    parseHeader() {
        let dv = this.dv;
        if (dv.byteLength < 22) throw new Error('File too small to be XTG/XTH');
        this.header = {
            mark:        dv.getUint32(0, true), // "XTG\0" or "XTH\0"
            width:       dv.getUint16(4, true),
            height:      dv.getUint16(6, true),
            colorMode:   dv.getUint8(8),
            compression: dv.getUint8(9),
            dataSize:    dv.getUint32(10, true),
        };

        if (this.header.mark !== 0x00475458 && this.header.mark !== 0x00485458) {
            throw new Error('Not an XTG/XTH Image');
        }
        if (this.header.colorMode !== 0) throw new Error('Unsupported colorMode');
        if (this.header.compression !== 0) throw new Error('Unsupported compression');
    }

    getImageData() {
        let dv = this.dv;
        let w = this.header.width;
        let h = this.header.height;
        const imgDataOffset = 22;

        if (imgDataOffset + this.header.dataSize > dv.byteLength) {
            throw new Error('Image data out of range');
        }

        const raw = new Uint8Array(this.buf, imgDataOffset, this.header.dataSize);
        const rgba = new Uint8ClampedArray(w * h * 4);

        if (this.header.mark === 0x00475458) {
            // XTG: 1bpp to RGBA
            const rowBytes = Math.floor((w + 7) / 8);
            for (let y = 0; y < h; y++) {
                const rowStart = y * rowBytes;
                for (let x = 0; x < w; x++) {
                    const byte = raw[rowStart + (x >> 3)];
                    const bit = (byte >> (7 - (x & 7))) & 1;
                    const v = bit ? 255 : 0;
                    const idx = (y * w + x) * 4;
                    rgba[idx] = v;
                    rgba[idx+1] = v;
                    rgba[idx+2] = v;
                    rgba[idx+3] = 255;
                }
            }
        } else if (this.header.mark === 0x00485458) {
            // XTH: 2-bit planes (4-level grayscale)
            const planeSize = Math.ceil((w * h) / 8);
            const plane1 = raw.subarray(0, planeSize);
            const plane2 = raw.subarray(planeSize, planeSize * 2);

            for (let x = 0; x < w; x++) {
                const col = w - 1 - x; // 反向
                for (let y = 0; y < h; y++) {
                    const byteIndex = (y >> 3) + col * Math.ceil(h / 8);
                    const bitIndex = y & 7;

                    const bit1 = (plane1[byteIndex] >> (7 - bitIndex)) & 1;
                    const bit2 = (plane2[byteIndex] >> (7 - bitIndex)) & 1;
                    // plane1存储bit1，plane2存储bit2，所以组合时应该匹配编码器
                    // 编码器: plane1存储高位(level & 2)，plane2存储低位(level & 1)
                    // 解码: pixelValue = (bit1 << 1) | bit2
                    let pixelValue = (bit1 << 1) | bit2;

                    // 映射到灰度（注意：1和2是反的，以匹配官方编码器）
                    let v;
                    switch (pixelValue) {
                        case 0: v = 255; break; // White
                        case 1: v = 85;  break; // Dark Grey
                        case 2: v = 170; break; // Light Grey
                        case 3: v = 0;   break; // Black
                    }

                    const idx = (y * w + x) * 4;
                    rgba[idx] = v;
                    rgba[idx+1] = v;
                    rgba[idx+2] = v;
                    rgba[idx+3] = 255;
                }
            }
        }

        return { width: w, height: h, data: rgba };
    }
}

class XTCViewer {
    constructor() {
        this.files = [];
        this.currentFile = null;
        this.currentPage = 0;
        this.totalPages = 0;
        this.zoom = 1.0;
        this.pages = [];
        this.xtcFile = null;
        this.fileBuffer = null;  // 缓存整个文件数据

        this.fileListEl = document.getElementById('fileList');
        this.pageInfoEl = document.getElementById('pageInfo');
        this.formatInfoEl = document.getElementById('formatInfo');
        this.readerContentEl = document.getElementById('readerContent');
        this.zoomLevelEl = document.getElementById('zoomLevel');

        this.init();
    }

    async init() {
        await this.loadFileList();
        this.setupKeyboardShortcuts();

        const urlParams = new URLSearchParams(window.location.search);
        const filePath = urlParams.get('path');
        const fileName = urlParams.get('file');
        const fileId = urlParams.get('id');

        if (fileId) {
            await this.loadXTCFileById(fileId);
        } else if (filePath) {
            await this.loadXTCFileByPath(filePath);
        } else if (fileName) {
            const targetFile = this.files.find(f => f.name === fileName);
            if (targetFile) {
                await this.selectFile(fileName);
            } else {
                this.showToast(`未找到文件: ${fileName}`);
            }
        }
    }

    async loadXTCFileById(fileId) {
        this.currentPage = 0;
        this.pages = [];
        this.fileBuffer = null;
        this.showLoading();

        try {
            const response = await fetch(`/api/xtc-view-single?id=${encodeURIComponent(fileId)}`);
            if (!response.ok) throw new Error('获取文件内容失败');

            const arrayBuffer = await response.arrayBuffer();
            this.fileBuffer = arrayBuffer;  // 缓存整个文件

            this.parseXTC(arrayBuffer);

            const fileName = response.headers.get('X-File-Name') || `File-${fileId}`;
            this.currentFile = { name: fileName, id: fileId };

            if (this.totalPages > 0) {
                this.showPage(0);
            }

        } catch (error) {
            console.error('加载XTC文件失败:', error);
            this.showError(`加载文件失败: ${error.message}`);
        }
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                this.prevPage();
            } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                this.nextPage();
            } else if (e.key === '+' || e.key === '=') {
                this.zoomIn();
            } else if (e.key === '-') {
                this.zoomOut();
            } else if (e.key === 'Escape') {
                this.resetZoom();
            }
        });
    }

    async loadFileList() {
        try {
            const response = await fetch('/api/xtc-files');
            if (!response.ok) throw new Error('获取文件列表失败');
            this.files = await response.json();
            this.renderFileList();
        } catch (error) {
            console.error('加载文件列表失败:', error);
            this.fileListEl.innerHTML = `
                <div class="empty-state">
                    <p>加载失败: ${error.message}</p>
                </div>
            `;
        }
    }

    renderFileList() {
        if (this.files.length === 0) {
            this.fileListEl.innerHTML = `
                <div class="empty-state">
                    <p>队列中没有XTC文件</p>
                </div>
            `;
            return;
        }

        this.fileListEl.innerHTML = this.files.map(file => `
            <div class="file-item ${this.currentFile?.name === file.name ? 'active' : ''}"
                 onclick="viewer.selectFile('${file.name}')">
                <div class="file-name">${file.name}</div>
                <div class="file-meta">
                    <span>${this.formatFileSize(file.size)}</span>
                    <span>${file.page_count || '?'} 页</span>
                </div>
            </div>
        `).join('');
    }

    async selectFile(fileName) {
        const file = this.files.find(f => f.name === fileName);
        if (!file) return;

        this.currentFile = file;
        this.currentPage = 0;
        this.pages = [];
        this.renderFileList();
        this.showLoading();

        try {
            await this.loadXTCFile(file.path);
        } catch (error) {
            console.error('加载XTC文件失败:', error);
            this.showError(`加载文件失败: ${error.message}`);
        }
    }

    async loadXTCFile(filePath) {
        const response = await fetch(`/api/xtc-view?path=${encodeURIComponent(filePath)}`);
        if (!response.ok) throw new Error('获取文件内容失败');

        const arrayBuffer = await response.arrayBuffer();
        this.fileBuffer = arrayBuffer;  // 缓存整个文件

        this.parseXTC(arrayBuffer);

        if (this.totalPages > 0) {
            this.showPage(0);
        }
    }

    parseXTC(arrayBuffer) {
        const dv = new DataView(arrayBuffer);

        // 检查文件大小（至少56字节）
        if (dv.byteLength < 56) {
            throw new Error('XTC文件太小');
        }

        // 解析文件头（48字节）
        const mark = dv.getUint32(0, true);
        if (mark !== 0x00435458 && mark !== 0x48435458) {
            throw new Error('不是有效的XTC文件');
        }

        const version = dv.getUint16(4, true);
        const pageCount = dv.getUint16(6, true);
        const readDirection = dv.getUint8(8);
        const hasMetadata = !!dv.getUint8(9);
        const hasThumbnails = !!dv.getUint8(10);
        const hasChapters = !!dv.getUint8(11);

        this.totalPages = pageCount;
        console.log(`解析XTC: ${pageCount}页`);

        // 读取偏移量
        const metadataOffset = Number(dv.getBigUint64(16, true));
        const indexOffset = Number(dv.getBigUint64(24, true));
        const dataOffset = Number(dv.getBigUint64(32, true));

        console.log(`偏移量: metadata=${metadataOffset}, index=${indexOffset}, data=${dataOffset}`);

        // 解析索引表（每个索引项16字节）
        this.pages = [];
        for (let i = 0; i < pageCount; i++) {
            const offset = indexOffset + i * 16;

            if (offset + 16 > dv.byteLength) {
                throw new Error('索引表超出范围');
            }

            const pageOffset = Number(dv.getBigUint64(offset, true));
            const pageSize = dv.getUint32(offset + 8, true);
            const width = dv.getUint16(offset + 12, true);
            const height = dv.getUint16(offset + 14, true);

            this.pages.push({
                offset: pageOffset,
                size: pageSize,
                width: width,
                height: height
            });
        }

        // 更新格式信息
        this.formatInfoEl.textContent = `XTC格式 · ${pageCount}页`;
    }

    showPage(pageNum) {
        if (pageNum < 0 || pageNum >= this.totalPages) return;

        this.currentPage = pageNum;
        const page = this.pages[pageNum];

        this.pageInfoEl.textContent = `${pageNum + 1} / ${this.totalPages}`;

        // 从缓存的buffer中提取页面数据并渲染
        if (!this.fileBuffer) {
            this.showError('文件数据未加载');
            return;
        }

        try {
            const entry = this.pages[pageNum];
            console.log(`显示页面 ${pageNum}: offset=${entry.offset}, size=${entry.size}, total=${this.fileBuffer.byteLength}`);

            // 验证偏移量是否在文件范围内
            if (entry.offset + entry.size > this.fileBuffer.byteLength) {
                throw new Error(`页面数据超出范围: ${entry.offset} + ${entry.size} > ${this.fileBuffer.byteLength}`);
            }

            const pageData = this.fileBuffer.slice(entry.offset, entry.offset + entry.size);
            console.log(`页面数据大小: ${pageData.byteLength}, 前4字节: ${Array.from(new Uint8Array(pageData.slice(0, 4))).map(b => b.toString(16).padStart(2, '0')).join('')}`);

            const xtgImage = new XTGH_Image(pageData);
            const { width, height, data } = xtgImage.getImageData();

            this.renderPageData(width, height, data);
        } catch (error) {
            console.error('渲染页面失败:', error);
            this.showError(`渲染页面失败: ${error.message}`);
        }
    }

    renderPageData(width, height, imageData) {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        canvas.className = 'page-canvas';

        const ctx = canvas.getContext('2d');
        const imgData = new ImageData(imageData, width, height);
        ctx.putImageData(imgData, 0, 0);

        canvas.style.transform = `scale(${this.zoom})`;

        this.readerContentEl.innerHTML = '';
        this.readerContentEl.appendChild(canvas);
    }

    showLoading() {
        this.pageInfoEl.textContent = '加载中...';
        this.readerContentEl.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <div>正在加载页面...</div>
            </div>
        `;
    }

    showError(message) {
        this.pageInfoEl.textContent = '加载失败';
        this.readerContentEl.innerHTML = `
            <div class="empty-state">
                <p>${message}</p>
            </div>
        `;
    }

    firstPage() {
        if (this.totalPages > 0) this.showPage(0);
    }

    lastPage() {
        if (this.totalPages > 0) this.showPage(this.totalPages - 1);
    }

    prevPage() {
        if (this.currentPage > 0) {
            this.showPage(this.currentPage - 1);
        } else {
            this.showToast('已经是第一页了');
        }
    }

    nextPage() {
        if (this.currentPage < this.totalPages - 1) {
            this.showPage(this.currentPage + 1);
        } else {
            this.showToast('已经是最后一页了');
        }
    }

    zoomIn() {
        this.zoom = Math.min(this.zoom + 0.25, 3.0);
        this.updateZoom();
        this.showToast(`放大: ${Math.round(this.zoom * 100)}%`);
    }

    zoomOut() {
        this.zoom = Math.max(this.zoom - 0.25, 0.5);
        this.updateZoom();
        this.showToast(`缩小: ${Math.round(this.zoom * 100)}%`);
    }

    resetZoom() {
        this.zoom = 1.0;
        this.updateZoom();
        this.showToast('已重置缩放');
    }

    updateZoom() {
        this.zoomLevelEl.textContent = `${Math.round(this.zoom * 100)}%`;
        const canvas = this.readerContentEl.querySelector('.page-canvas');
        if (canvas) {
            canvas.style.transform = `scale(${this.zoom})`;
        }
    }

    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    showToast(message) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 2000);
    }
}

let viewer;
document.addEventListener('DOMContentLoaded', () => {
    viewer = new XTCViewer();
});

function refreshFileList() {
    viewer.loadFileList();
    viewer.showToast('列表已刷新');
}

function firstPage() {
    viewer.firstPage();
}

function lastPage() {
    viewer.lastPage();
}

function prevPage() {
    viewer.prevPage();
}

function nextPage() {
    viewer.nextPage();
}

function zoomIn() {
    viewer.zoomIn();
}

function zoomOut() {
    viewer.zoomOut();
}

function resetZoom() {
    viewer.resetZoom();
}
