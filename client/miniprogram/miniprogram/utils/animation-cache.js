/**
 * 动图本地缓存管理器
 * 将远程 GIF 动画下载到本地用户目录，后续直接使用本地路径显示
 * 目的：提升加载速度、支持离线查看、减少网络流量
 */
const fs = wx.getFileSystemManager();
const ANIM_CACHE_DIR = `${wx.env.USER_DATA_PATH}/animations`;
const CACHE_MAP_KEY = 'anim_cache_map';

// 内存中的 URL → 本地路径映射，避免频繁读写 storage
let _cacheMap = null;
// 正在下载中的 URL 集合，避免重复下载
const _downloading = new Set();
// 下载队列并发控制
let _activeDownloads = 0;
const MAX_CONCURRENT = 5;
const _pendingQueue = [];

/** 初始化缓存目录 */
function _ensureDir() {
  try {
    fs.accessSync(ANIM_CACHE_DIR);
  } catch (_) {
    fs.mkdirSync(ANIM_CACHE_DIR, true);
  }
}

/** 从 storage 加载缓存映射 */
function _loadMap() {
  if (_cacheMap) return _cacheMap;
  try {
    const raw = wx.getStorageSync(CACHE_MAP_KEY);
    _cacheMap = raw ? JSON.parse(raw) : {};
  } catch (_) {
    _cacheMap = {};
  }
  return _cacheMap;
}

/** 持久化缓存映射到 storage */
function _saveMap() {
  try {
    wx.setStorageSync(CACHE_MAP_KEY, JSON.stringify(_cacheMap));
  } catch (e) {
    console.warn('[anim-cache] 保存缓存映射失败:', e);
  }
}

/**
 * 从 URL 提取唯一文件名（用 URL 的 hash 部分或路径尾部）
 * @param {string} url 远程 URL
 * @returns {string} 本地文件名
 */
function _urlToFileName(url) {
  // 取 URL 路径的最后一段作为基础名，去除查询参数
  const pathPart = url.split('?')[0];
  const segments = pathPart.split('/');
  let name = segments[segments.length - 1] || 'unknown';
  // 如果没有扩展名，默认 .gif
  if (!name.includes('.')) name += '.gif';
  // 添加 URL 的简单 hash 防冲突
  let hash = 0;
  for (let i = 0; i < url.length; i++) {
    hash = ((hash << 5) - hash) + url.charCodeAt(i);
    hash |= 0;
  }
  const hashStr = Math.abs(hash).toString(36).substring(0, 4);
  // 将 hash 插入文件名中：xxx.gif → xxx_a1b2.gif
  const dotIdx = name.lastIndexOf('.');
  if (dotIdx > 0) {
    name = name.substring(0, dotIdx) + '_' + hashStr + name.substring(dotIdx);
  } else {
    name = name + '_' + hashStr;
  }
  return name;
}

/**
 * 下载单个动画文件到本地，带并发控制
 * @param {string} url 远程 URL
 * @returns {Promise<string>} 本地文件路径
 */
function _downloadOne(url) {
  return new Promise((resolve, reject) => {
    const run = () => {
      _activeDownloads++;
      const localName = _urlToFileName(url);
      const localPath = `${ANIM_CACHE_DIR}/${localName}`;

      wx.downloadFile({
        url,
        timeout: 30000,
        success(res) {
          if (res.statusCode === 200 && res.tempFilePath) {
            // 保存到永久目录
            try {
              fs.saveFileSync(res.tempFilePath, localPath);
              _loadMap()[url] = localPath;
              _saveMap();
              console.log('[anim-cache] 已缓存:', localName);
              resolve(localPath);
            } catch (e) {
              // saveFileSync 失败时尝试直接使用 tempFilePath
              console.warn('[anim-cache] 保存文件失败，使用临时路径:', e);
              _loadMap()[url] = res.tempFilePath;
              _saveMap();
              resolve(res.tempFilePath);
            }
          } else {
            console.warn('[anim-cache] 下载失败 HTTP', res.statusCode, url.substring(0, 60));
            reject(new Error(`下载失败: HTTP ${res.statusCode}`));
          }
        },
        fail(err) {
          console.warn('[anim-cache] 下载出错:', url.substring(0, 60), err.errMsg);
          reject(err);
        },
        complete() {
          _activeDownloads--;
          _downloading.delete(url);
          _drainQueue();
        }
      });
    };

    // 加入下载队列
    if (_activeDownloads < MAX_CONCURRENT) {
      _downloading.add(url);
      run();
    } else {
      _pendingQueue.push(run);
    }
  });
}

/** 处理下载队列 */
function _drainQueue() {
  while (_activeDownloads < MAX_CONCURRENT && _pendingQueue.length > 0) {
    const next = _pendingQueue.shift();
    next();
  }
}

/**
 * 获取动画的本地路径（优先缓存，无缓存时触发下载）
 * @param {string} url 远程 URL
 * @returns {Promise<string>} 本地路径（如果下载失败返回原 URL 作为回退）
 */
async function getLocalPath(url) {
  if (!url) return '';
  // 已经是本地路径或云文件 ID，直接返回
  if (url.startsWith(wx.env.USER_DATA_PATH) || url.startsWith('cloud://')) return url;

  const map = _loadMap();
  // 命中缓存
  if (map[url]) {
    // 检查文件是否存在
    try {
      fs.accessSync(map[url]);
      return map[url];
    } catch (_) {
      // 文件不存在，删除过期映射
      delete map[url];
      _saveMap();
    }
  }

  // 正在下载中，等待完成
  if (_downloading.has(url)) {
    // 轮询等待（最多 30 次 × 200ms = 6s）
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 200));
      const updated = _loadMap();
      if (updated[url]) return updated[url];
    }
    // 超时返回原 URL
    return url;
  }

  // 触发下载
  try {
    return await _downloadOne(url);
  } catch (_) {
    // 下载失败回退到远程 URL
    return url;
  }
}

/**
 * 同步获取本地路径（仅查缓存，不触发下载）
 * @param {string} url 远程 URL
 * @returns {string} 本地路径或原 URL
 */
function getLocalPathSync(url) {
  if (!url) return '';
  if (url.startsWith(wx.env.USER_DATA_PATH) || url.startsWith('cloud://')) return url;
  const map = _loadMap();
  if (map[url]) {
    try {
      fs.accessSync(map[url]);
      return map[url];
    } catch (_) {
      delete map[url];
      _saveMap();
    }
  }
  return url;
}

/**
 * 批量预加载动画到本地（并行下载，带并发控制）
 * @param {string[]} urls 需要预加载的远程 URL 列表
 * @returns {Promise<{success: number, fail: number}>}
 */
async function preloadUrls(urls) {
  if (!urls || urls.length === 0) return { success: 0, fail: 0 };
  _ensureDir();

  // 过滤掉不需要下载的 URL
  const toDownload = urls.filter(u => {
    if (!u) return false;
    if (u.startsWith(wx.env.USER_DATA_PATH) || u.startsWith('cloud://')) return false;
    const map = _loadMap();
    if (map[u]) {
      try { fs.accessSync(map[u]); return false; } catch (_) { delete map[u]; }
    }
    return true;
  });

  if (toDownload.length === 0) {
    console.log('[anim-cache] 所有动画已缓存，无需下载');
    return { success: 0, fail: 0 };
  }

  console.log(`[anim-cache] 开始预加载 ${toDownload.length} 个动画文件...`);

  let success = 0;
  let fail = 0;

  const results = await Promise.allSettled(
    toDownload.map(url => _downloadOne(url))
  );

  results.forEach(r => {
    if (r.status === 'fulfilled') success++;
    else fail++;
  });

  console.log(`[anim-cache] 预加载完成: 成功 ${success}, 失败 ${fail}`);
  return { success, fail };
}

/**
 * 从页面数据中提取所有动画 URL
 * @param {Object} pageData 格式化后的页面数据（_formatPageData 返回的结构）
 * @returns {string[]} 去重后的动画 URL 列表
 */
function extractAnimUrls(pageData) {
  const urls = [];
  const add = (u) => { if (u) urls.push(u); };

  add(pageData.background_anim_url);
  add(pageData.animation_url);

  // 句子中的角色动画
  if (pageData.sentences) {
    pageData.sentences.forEach(s => add(s.animation_url));
  }

  // character_animations 映射
  if (pageData.character_animations) {
    Object.values(pageData.character_animations).forEach(v => add(v));
  }

  return [...new Set(urls)];
}

/**
 * 将格式化的页面数据中的 URL 替换为本地路径（同步，仅对已缓存文件有效）
 * @param {Object} pageData 页面数据
 */
function applyCacheToPage(pageData) {
  if (pageData.background_anim_url) {
    pageData.background_anim_url = getLocalPathSync(pageData.background_anim_url);
  }
  if (pageData.animation_url) {
    pageData.animation_url = getLocalPathSync(pageData.animation_url);
  }
  if (pageData.sentences) {
    pageData.sentences.forEach(s => {
      if (s.animation_url) {
        s.animation_url = getLocalPathSync(s.animation_url);
      }
    });
  }
  if (pageData.character_animations) {
    const updated = {};
    for (const [key, val] of Object.entries(pageData.character_animations)) {
      updated[key] = getLocalPathSync(val);
    }
    pageData.character_animations = updated;
  }
}

/**
 * 清除所有缓存动画
 */
function clearCache() {
  try {
    // 删除动画目录
    try {
      fs.rmdirSync(ANIM_CACHE_DIR, true);
    } catch (_) {}
    // 清除映射
    wx.removeStorageSync(CACHE_MAP_KEY);
    _cacheMap = {};
    console.log('[anim-cache] 缓存已清除');
  } catch (e) {
    console.warn('[anim-cache] 清除缓存失败:', e);
  }
}

/**
 * 获取缓存统计
 * @returns {{count: number, totalSize: number}}
 */
function getCacheStats() {
  const map = _loadMap();
  let totalSize = 0;
  let validCount = 0;
  for (const [url, path] of Object.entries(map)) {
    try {
      const stat = fs.statSync(path);
      totalSize += stat.size;
      validCount++;
    } catch (_) {
      delete map[url];
    }
  }
  if (validCount !== Object.keys(map).length) _saveMap();
  return { count: validCount, totalSize };
}

module.exports = {
  getLocalPath,
  getLocalPathSync,
  preloadUrls,
  extractAnimUrls,
  applyCacheToPage,
  clearCache,
  getCacheStats,
};
