/**
 * 将 Hugo 生成的 JSON Canvas 接入只读阅读器。
 * 页面加载异常会显示可读提示，节点资源异常限制在该节点内。
 */
import { JSONCanvasViewer, parser } from 'json-canvas-viewer';

/**
 * 将 Markdown 解析结果中的相对地址解析到其发布画布目录。
 * @param {string} markdown 已转换引用的 Markdown 正文。
 * @param {URL} baseURL 画布 JSON 的绝对地址。
 * @returns {Promise<string>} 经上游 DOMPurify 净化并修正地址的 HTML。
 * @throws {Error} Markdown 解析失败时向调用方传播。
 */
async function renderMarkdown(markdown, baseURL) {
    const template = document.createElement('template');
    template.innerHTML = await parser(markdown);
    for (const element of template.content.querySelectorAll('[href], [src]')) {
        const attribute = element.hasAttribute('href') ? 'href' : 'src';
        const value = element.getAttribute(attribute);
        // 页内锚点留给节点内的滚动处理，避免跳到整张画布的页面顶部。
        if (!value || value.startsWith('#')) continue;
        const url = new URL(value, baseURL);
        if (!['http:', 'https:', 'mailto:', 'tel:'].includes(url.protocol)) {
            element.removeAttribute(attribute);
            continue;
        }
        element.setAttribute(attribute, url.href);
        if (element.tagName === 'A' && url.origin !== location.origin) {
            element.setAttribute('target', '_blank');
            element.setAttribute('rel', 'noopener noreferrer');
        }
    }
    for (const heading of template.content.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
        heading.id = heading.textContent.toLowerCase().replace(/[^\p{L}\p{N}_\- ]/gu, '').replace(/ /g, '-');
    }
    return template.innerHTML;
}

/**
 * 创建可在画布中滚动、并支持节点内锚点的 Markdown 容器。
 * @param {HTMLElement} container 上游提供的节点容器。
 * @returns {HTMLDivElement} 用于填充净化后 HTML 的正文元素。
 * @throws {Error} 无预期异常。
 */
function markdownContainer(container) {
    container.classList.add('JCV-markdown-content');
    const content = document.createElement('div');
    content.className = 'JCV-parsed-content-wrapper';
    content.addEventListener('click', event => {
        const anchor = event.target.closest('a[href^="#"]');
        if (!anchor) return;
        const id = decodeURIComponent(anchor.hash.slice(1));
        const heading = [...content.querySelectorAll('[id]')].find(element => element.id === id);
        if (heading) {
            event.preventDefault();
            heading.scrollIntoView({ block: 'nearest' });
        }
    });
    container.append(content);
    return content;
}

/**
 * 创建清晰可点击的链接，外部网页在新标签页打开。
 * @param {string} href 目标地址。
 * @param {string} label 链接显示文字。
 * @returns {HTMLAnchorElement} 带有必要浏览上下文属性的链接。
 * @throws {TypeError} href 无法解析为 URL 时抛出。
 */
function readingLink(href, label) {
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.textContent = label;
    if (new URL(href, location.href).origin !== location.origin) {
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
    }
    return anchor;
}

/**
 * 初始化当前页面的只读画布及查看控件。
 * @returns {Promise<void>} 初始化完成后兑现；错误转为页面状态提示。
 * @throws {Error} 无未处理异常，读取或渲染错误由本函数捕获。
 */
async function initializeReader() {
    const host = document.getElementById('canvas-host');
    if (!host) return;
    const shell = document.getElementById('canvas-reader');
    const status = document.getElementById('canvas-status');
    const scale = document.getElementById('canvas-scale');
    const fullscreenButton = shell.querySelector('[data-action="fullscreen"]');
    let viewer;
    let themeObserver;
    let expanded = false;
    let disposed = false;
    try {
        const baseURL = new URL(host.dataset.source, location.href);
        const response = await fetch(baseURL);
        if (!response.ok) throw new Error(`画布数据请求失败（HTTP ${response.status}）`);
        const data = await response.json();
        if (!Array.isArray(data.nodes) || !Array.isArray(data.edges)) throw new Error('画布数据缺少 nodes 或 edges');
        if (!data.nodes.length) {
            // 上游以节点边界计算初始比例，空画布没有有限边界，直接显示空状态。
            host.setAttribute('aria-busy', 'false');
            shell.dataset.state = 'ready';
            status.textContent = '这是一张空画布。';
            return;
        }
        const attachments = {};
        for (const node of data.nodes) {
            if (node.type === 'file') {
                const url = new URL(node.file, baseURL);
                const name = decodeURIComponent(url.pathname.split('/').pop());
                // 上游用原始文件名判断类型，再通过 attachments 加载真实 URL。
                // 因而这里将编码地址与中文显示名称分开，避免文件标题出现百分号编码。
                if (/\.(png|jpe?g|gif|svg|webp|avif|bmp|ico|heic|heif|md|mdx|markdown|txt|mp3|wav|ogg|opus|aac|m4a|flac|mp4|webm|ogv|mov|m3u8|mpd)$/i.test(name)) {
                    const key = decodeURIComponent(node.file);
                    attachments[key] = url.href;
                    node.file = key;
                } else {
                    // 嵌套 Canvas、PDF 和其他附件采用链接卡片，保持站内跳转能力。
                    node.type = 'link';
                    node.url = url.href;
                }
                if (node.website) node.website = new URL(node.website, baseURL).href;
            }
            if (node.type === 'link') node.url = new URL(node.url, baseURL).href;
        }
        viewer = new JSONCanvasViewer({
            container: host,
            canvas: data,
            attachments,
            theme: document.documentElement.dataset.scheme === 'dark' ? 'dark' : 'light',
            parser: markdown => renderMarkdown(markdown, baseURL),
            pointeract: { proControlSchema: false, lockControlSchema: true },
            nodeComponents: {
                text: ({ container, content }) => {
                    markdownContainer(container).innerHTML = content;
                },
                image: ({ container, content, node }) => {
                    const image = document.createElement('img');
                    image.className = 'JCV-img';
                    image.src = content;
                    image.alt = decodeURIComponent(new URL(content, baseURL).pathname.split('/').pop());
                    image.loading = 'eager';
                    image.draggable = false;
                    image.addEventListener('error', () => {
                        const notice = document.createElement('p');
                        notice.className = 'canvas-node-notice';
                        notice.textContent = `图片加载失败：${image.alt}`;
                        container.append(notice);
                    }, { once: true });
                    // 完整显示截图，不使用上游默认的 cover 裁切长图。
                    container.append(image, readingLink(content, '查看原图 ↗'));
                    container.lastElementChild.className = 'canvas-original-image';
                    container.dataset.nodeId = node.id;
                },
                markdown: async ({ container, content, node, onBeforeUnmount }) => {
                    const wrapper = markdownContainer(container);
                    const abort = new AbortController();
                    onBeforeUnmount.subscribe(() => abort.abort());
                    wrapper.textContent = '正在加载笔记…';
                    try {
                        const note = await fetch(content, { signal: abort.signal });
                        if (!note.ok) throw new Error(`HTTP ${note.status}`);
                        wrapper.innerHTML = await renderMarkdown(await note.text(), baseURL);
                        if (node.website) wrapper.prepend(readingLink(node.website, '打开完整笔记 ↗'));
                        if (node.subpath?.startsWith('#')) {
                            const id = decodeURIComponent(node.subpath.slice(1));
                            const heading = [...wrapper.querySelectorAll('[id]')].find(element => element.id === id);
                            if (heading) wrapper.scrollTop = heading.offsetTop;
                        }
                    } catch (error) {
                        if (!abort.signal.aborted) wrapper.textContent = `笔记加载失败：${error.message}`;
                    }
                },
                link: ({ container, content }) => {
                    const card = document.createElement('div');
                    card.className = 'canvas-link-card';
                    const url = new URL(content, baseURL);
                    card.append(readingLink(url.href, '打开链接 ↗'));
                    const address = document.createElement('p');
                    address.textContent = decodeURI(url.href);
                    card.append(address);
                    container.append(card);
                },
            },
        });

        /** 更新缩放读数，不修改上游内部状态；无参数、返回值或预期异常。 */
        const updateScale = () => {
            const transform = host.querySelector('.JCV-overlays')?.style.transform;
            if (transform) scale.value = `${Math.round(new DOMMatrix(transform).a * 100)}%`;
        };
        /** 让所有节点回到可见区域；无参数、返回值或预期异常。 */
        const fit = () => { viewer.resetView(); viewer.refresh(); };
        /** 同步全屏按钮，并在布局稳定后重新适应画布；无参数、返回值或预期异常。 */
        const synchronizeFullscreen = () => {
            const active = document.fullscreenElement === shell || expanded;
            fullscreenButton.textContent = active ? '退出全屏' : '全屏';
            fullscreenButton.setAttribute('aria-pressed', String(active));
            requestAnimationFrame(() => requestAnimationFrame(fit));
        };
        shell.addEventListener('click', async event => {
            const button = event.target.closest('button[data-action]');
            if (!button) return;
            const center = { x: host.clientWidth / 2, y: host.clientHeight / 2 };
            switch (button.dataset.action) {
                case 'in': viewer.zoom(1.25, center); break;
                case 'out': viewer.zoom(0.8, center); break;
                case 'actual': viewer.zoomToScale(1, center); break;
                case 'fit': fit(); break;
                case 'fullscreen':
                    try {
                        if (document.fullscreenElement) await document.exitFullscreen();
                        else if (expanded) expanded = false;
                        else if (document.fullscreenEnabled) await shell.requestFullscreen();
                        else expanded = true;
                    } catch {
                        expanded = !expanded;
                    }
                    shell.classList.toggle('canvas-expanded', expanded);
                    synchronizeFullscreen();
                    break;
            }
        });
        shell.addEventListener('keydown', event => {
            if (event.target.closest('a,button,input,textarea,select')) return;
            const action = { '+': 'in', '=': 'in', '-': 'out', '0': 'fit', 'f': 'fullscreen' }[event.key];
            if (action) {
                event.preventDefault();
                shell.querySelector(`[data-action="${action}"]`).click();
            }
            if (event.key === 'Escape' && expanded) {
                expanded = false;
                shell.classList.remove('canvas-expanded');
                synchronizeFullscreen();
            }
        });
        document.addEventListener('fullscreenchange', synchronizeFullscreen);
        themeObserver = new MutationObserver(() => {
            viewer.changeTheme(document.documentElement.dataset.scheme === 'dark' ? 'dark' : 'light');
        });
        themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-scheme'] });
        viewer.onRefresh.subscribe(updateScale);
        shell.querySelectorAll('button[data-action]').forEach(button => { button.disabled = false; });
        host.setAttribute('aria-busy', 'false');
        shell.dataset.state = 'ready';
        status.textContent = data.nodes.length ? '' : '这是一张空画布。';
        if (data.nodes.length) fit();
        window.addEventListener('pagehide', event => {
            // 保留浏览器前进后退缓存中的实例；真正离开时释放观察器及动画循环。
            if (event.persisted) return;
            disposed = true;
            themeObserver.disconnect();
            document.removeEventListener('fullscreenchange', synchronizeFullscreen);
            viewer.dispose();
        });
    } catch (error) {
        if (disposed) return;
        themeObserver?.disconnect();
        viewer?.dispose();
        host.setAttribute('aria-busy', 'false');
        shell.dataset.state = 'error';
        status.textContent = `画布加载失败：${error.message}。请刷新页面重试，或下载数据。`;
    }
}

initializeReader();
