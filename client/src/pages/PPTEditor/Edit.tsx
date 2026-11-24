// PPT 编辑页 — 逐页浏览 + SVG-native PPTX 导出 + 主题/版本管理 + PPTX 预览
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teacherApi, PPTDetail, ThemeItem, PptVersionItem } from '../../api/teacher';
import SlidePreview from './SlidePreview';
import SVGEditor from './SVGEditor';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSecondary, btnDanger, btnSmall, btnSmallSecondary,
  IconEdit, IconBack, IconCheck, IconPlay, IconArrowRight, IconPpt, IconRefresh,
} from '../../design-system';

const SLIDE_TYPE_LABELS: Record<string, string> = {
  title: '标题页', objective: '学习目标', vocabulary: '词汇展示',
  dialogue: '对话练习', grammar: '语法讲解', practice: '课堂练习',
  interactive: '互动活动', summary: '总结回顾',
  listening: '听力练习', speaking: '口语跟读',
  ai_interaction: 'AI 互动',
};

const THEME_NAMES: Record<string, string> = {
  classic: '经典简约', cartoon: '卡通童趣', academic: '学术严谨',
  senior: '沉稳大气', blackboard: '黑板风格', warm: '温馨暖色',
  tech: '科技感', nature: '自然清新', business: '商务专业',
};

export default function PPTEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [ppt, setPpt] = useState<PPTDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [regenerating, setRegenerating] = useState(false);
  const [themes, setThemes] = useState<ThemeItem[]>([]);
  const [showThemeMenu, setShowThemeMenu] = useState(false);
  const [changingTheme, setChangingTheme] = useState(false);
  const [versions, setVersions] = useState<PptVersionItem[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showAudioText, setShowAudioText] = useState(false);
  const [showEditor, setShowEditor] = useState(false);

  // HTML 版 PPT 预览（iframe 渲染）
  const [htmlContent, setHtmlContent] = useState('');
  const [iframeReady, setIframeReady] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const pendingPageRef = useRef<number | null>(null);
  const pendingToggleRef = useRef<boolean | null>(null);

  // 可视化编辑模式
  const [visualEditMode, setVisualEditMode] = useState(false);
  const [selectedElInfo, setSelectedElInfo] = useState<{
    tag: string; text: string; x: number; y: number; w: number; h: number;
  } | null>(null);
  const [editTextVal, setEditTextVal] = useState('');
  const [editXVal, setEditXVal] = useState(0);
  const [editYVal, setEditYVal] = useState(0);
  const [editFontSize, setEditFontSize] = useState(16);
  // 存储当前值 ref 供拖拽闭包内使用（必须在 state 声明之后）
  const selInfoRef = useRef(selectedElInfo);
  const editTextValRef = useRef(editTextVal);
  const editFontSizeRef = useRef(editFontSize);
  const currentPageRef = useRef(currentPage);
  // 右键菜单弹出位置（屏幕坐标），null 时不显示弹出
  const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(null);

  // 编辑追踪：每个页面已修改的元素列表
  const [editsMap, setEditsMap] = useState<Record<string, { tag: string; text?: string; x?: number; y?: number; fontSize?: number }[]>>({});
  const [savingVisual, setSavingVisual] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      teacherApi.ppt.get(id),
      teacherApi.ppt.listThemes({ page_size: 50 }).catch(() => ({ items: [], total: 0 })),
    ])
      .then(([pptData, themeData]) => {
        setPpt(pptData);
        setThemes(themeData.items);
      })
      .catch((e: any) => alert('加载失败: ' + e.message))
      .finally(() => setLoading(false));
  }, [id]);

  // 构建注入脚本（编辑模式 + 拖拽 + 元素选择）
  const buildInjectCode = useCallback((origin: string) => {
    // 策略：劫持 addEventListener 记录 IIFE 注册在 document 上的 click 处理器，
    // 编辑模式下用 removeEventListener 物理移除，退出时重新装上。
    // 这比 stopImmediatePropagation 更可靠——处理器直接不存在了，不可能被触发。
    const lines = [
      'window.BACKEND_BASE="' + origin + '";window.__editMode=false;window.__editsMap={};window.__backCurrent=0;',
      // ---- 阶段0：addEventListener 劫持（在一切代码之前运行）----
      // 记录 document 上所有 click 处理器的引用，以便编辑模式时物理移除
      '(function(){',
      'var _origAE=EventTarget.prototype.addEventListener;',
      'var _tracked=[];',             // [{handler, options}] — IIFE 注册的处理器
      'var _skipTrack=false;',        // 我们自己的处理器跳过记录
      'var _removed=false;',          // 当前是否已移除 tracked 处理器
      'EventTarget.prototype.addEventListener=function(t,h,o){',
      'if(t==="click"&&this===document&&!_skipTrack&&!o){',
      '_tracked.push({h:h,o:o});',
      '}',
      'return _origAE.call(this,t,h,o);',
      '};',
      // 暴露两个方法给后续代码使用
      'window.__removeNavHandlers=function(){',
      'if(_removed)return;_removed=true;',
      '_tracked.forEach(function(x){document.removeEventListener("click",x.h,x.o)});',
      '};',
      'window.__restoreNavHandlers=function(){',
      'if(!_removed)return;_removed=false;',
      '_tracked.forEach(function(x){document.addEventListener("click",x.h,x.o)});',
      '};',
      '})();',
      // ---- 阶段1：核心编辑器 IIFE ----
      '(function(){',
      'try{', // 顶层 catch 捕获任何初始化异常
      'console.log("[EDIT] IIFE loaded, document.readyState="+document.readyState);',
      'var sel=null,cssEl=null;',
      // CSS
      'function ensureCss(active){',
      'if(active){if(!cssEl){cssEl=document.createElement("style");cssEl.id="__edit_css";',
      'cssEl.textContent=".__el_selected{outline:3px solid #2196F3!important;outline-offset:2px!important;position:relative;z-index:10}',
      '.slide-content>*:hover{outline:1px dashed #90CAF9;cursor:pointer}";',
      'document.head.appendChild(cssEl)}}else{if(cssEl){cssEl.remove();cssEl=null}}}',
      // 辅助
      'function getRelPos(el){',
      'if(!el)return{x:0,y:0,w:0,h:0};',
      'var slide=el.closest(".ppt-slide")||document.querySelector(".ppt-slide-container")||document.querySelector(".ppt-slide");',
      'var sr=slide?slide.getBoundingClientRect():{left:0,top:0};',
      'var er=el.getBoundingClientRect();',
      'return{x:Math.round(er.left-sr.left),y:Math.round(er.top-sr.top),w:Math.round(er.width),h:Math.round(er.height)}}',
      'function findEditable(el){',
      'if(!el)return null;',
      'return el.closest(".slide-content>*")||el.closest(".slide-title>*")||el.closest(".vocab-grid>*")||el.closest(".dialogue-cards>*")||el.closest(".grammar-card")||el.closest(".word-card")||el.closest(".ai-questions-wrap>*")||el.closest("h1,h2,h3,h4,h5,h6,p,span,li")}',
      'function isInteractive(el){return!!(el&&(el.closest(".audio-play-btn")||el.closest(".option-item")||el.closest(".question-card")||el.closest(".audio-expand-btn")||el.closest("button")||el.closest("a")||el.closest("input")||el.closest("select")||el.closest("textarea")))}',
      'function clearSel(){if(sel){sel.classList.remove("__el_selected");sel=null}}',
      // ===== click 捕获阶段：元素选择 =====
      'document.addEventListener("click",function(e){',
      'try{',
      'console.log("[EDIT] click fired",e.target.tagName,e.target.className,window.__editMode);',
      'if(!window.__editMode)return;',
      'var t=e.target;if(isInteractive(t))return;',
      'e.stopPropagation();e.preventDefault();',
      'var el=findEditable(t);',
      'console.log("[EDIT] findEditable result",el,el?"tag="+el.tagName+" class="+el.className:"");',
      'if(!el||isInteractive(el))return;',
      'clearSel();sel=el;el.classList.add("__el_selected");',
      'var pos=getRelPos(el);',
      'console.log("[EDIT] element selected",el.tagName,pos);',
      'window.parent.postMessage({type:"element-selected",tag:el.tagName.toLowerCase(),text:el.textContent.trim(),pos:pos},"*");',
      '}catch(ce){console.warn("[edit] click error",ce)}',
      '},true);',
      // ===== mousedown：通知父窗口（不再支持拖拽）=====
      'document.addEventListener("mousedown",function(ev){',
      'window.parent.postMessage({type:"iframe-mousedown"},"*");',
      '});',
      // ===== contextmenu：右键弹出编辑窗口 =====
      'document.addEventListener("contextmenu",function(e){',
      'if(!window.__editMode)return;e.preventDefault();',
      'var t=e.target;var el=findEditable(t);if(!el||isInteractive(el))return;',
      'clearSel();sel=el;el.classList.add("__el_selected");',
      'var pos=getRelPos(el);var fs=parseFloat(window.getComputedStyle(el).fontSize);',
      'window.parent.postMessage({',
      'type:"element-contextmenu",tag:el.tagName.toLowerCase(),',
      'text:el.textContent.substr(0,5000).trim(),',
      'pos:pos,mouseX:e.clientX,mouseY:e.clientY,',
      'fontSize:isNaN(fs)?16:fs',
      '},"*");',
      '},true);',
      // ===== dblclick：编辑模式下阻止双击全屏 =====
      'document.addEventListener("dblclick",function(e){if(window.__editMode){e.stopPropagation();e.preventDefault()}},true);',
      // ===== keydown：编辑模式下阻止空格翻页 =====
      'document.addEventListener("keydown",function(e){',
      'if(!window.__editMode)return;',
      '/* 阻止空格翻页 */',
      'if(e.key===" "){e.stopPropagation();e.preventDefault()}',
      '},true);',
      // ===== postMessage =====
      'window.addEventListener("message",function(ev){',
      'var d=ev.data||{};',
      // toggle-edit：物理移除/恢复 IIFE 的翻页 click 处理器
      'if(d.type==="toggle-edit"){',
      'console.log("[EDIT] toggle-edit",d.active);',
      'window.__editMode=d.active;ensureCss(d.active);',
      'if(d.active){window.__removeNavHandlers()}else{window.__restoreNavHandlers()}',
      'if(!d.active){clearSel()}',
      'return}',
      'if(d.type==="update-element"&&sel){',
      'if(d.text!==undefined)sel.textContent=d.text;',
      'if(d.fontSize!==undefined)sel.style.fontSize=d.fontSize+"px";return}',
      'if(d.type==="clear-selection"){clearSel();return}',
      // sync-page：父窗口已直接操作 DOM 切换页面，这里仅同步内部状态和清理残留动画样式
      // （不调用 goToPage 以避免 rAF 延迟回调在用户切换页面后覆盖当前 DOM 状态）
      'if(d.type==="sync-page"){',
      'var gs=document.querySelectorAll(".ppt-slide");',
      'if(gs.length&&d.index>=0&&d.index<gs.length){',
      'gs.forEach(function(s,i){',
      's.classList.toggle("active",i===d.index);',
      's.style.display=i===d.index?"flex":"none";',
      's.style.opacity=i===d.index?"1":"0";',
      // 清除 goToPage 动画可能残留的 transform / transition，防止幻灯片被推出视口
      's.style.transform="";',
      's.style.transition="";',
      '});',
      // 同步后端的 current 变量（用于键盘翻页等）
      'if(typeof current!=="undefined")current=d.index;',
      'window.__backCurrent=d.index;',
      '}',
      'return}',
      // 保留 go-to-page 兼容旧消息（不再由父组件发送，但保留以防其他地方使用）
      'if(d.type==="go-to-page"){',
      'var gs2=document.querySelectorAll(".ppt-slide");',
      'if(gs2.length&&d.index>=0&&d.index<gs2.length){',
      'if(typeof goToPage==="function"){goToPage(d.index,d.index>window.__backCurrent?"left":"right")}else{',
      'gs2.forEach(function(s,i){s.classList.toggle("active",i===d.index);s.style.display=i===d.index?"flex":"none";s.style.opacity=i===d.index?"1":"0"});',
      '}',
      'window.__backCurrent=d.index;',
      '}',
      'return}',
      'if(d.type==="collect-state"){var modified=[];document.querySelectorAll(".__el_selected,[data-el-modified]").forEach(function(el){var pos=getRelPos(el);var fs=parseFloat(window.getComputedStyle(el).fontSize);modified.push({tag:el.tagName.toLowerCase(),text:el.textContent.trim(),x:pos.x,y:pos.y,fontSize:isNaN(fs)?16:fs})});ev.source.postMessage({type:"collected-state",modified:modified},"*");return}',
      // apply-stored：仅在当前活跃幻灯片内查找元素
      'if(d.type==="apply-stored"&&d.edits){',
      'var activeSlide=document.querySelector(".ppt-slide.active")||document.querySelector(".ppt-slide");',
      'd.edits.forEach(function(ed){try{var scope=activeSlide||document.body;var els=scope.querySelectorAll(ed.tag);if(els.length>0){var el=els[0];if(ed.text!==undefined)el.textContent=ed.text;if(ed.x!==undefined&&ed.y!==undefined)el.style.transform="translate("+ed.x+"px,"+ed.y+"px)";if(ed.fontSize!==undefined)el.style.fontSize=ed.fontSize+"px";el.setAttribute("data-el-modified","1")}}catch(e){}});}',
      '});',
      'window.parent.postMessage({type:"slide-ready"},"*");',
      '}catch(e0){console.warn("[edit] IIFE init error",e0)}',
      '})();',
    ];
    return lines.join('');
  }, []);

  // 构建 HTML 版 PPT 预览内容
  useEffect(() => {
    if (!ppt?.html_content) return;
    const origin = window.location.origin;
    const injectCode = buildInjectCode(origin);
    let enhanced = ppt.html_content;
    // 优先替换 {backend_base_script} 占位符（新生成的 HTML）
    if (enhanced.includes('{backend_base_script}')) {
      enhanced = enhanced.replace('{backend_base_script}', injectCode);
    } else {
      // 容错：对旧版 HTML（占位符已被后端替换为 ""），在 </body> 前注入脚本
      enhanced = enhanced.replace('</body>', '<script>' + injectCode + '</script>\n</body>');
    }
    setHtmlContent(enhanced);
    setIframeReady(false);
    setEditsMap({}); // 重置编辑追踪
    setSelectedElInfo(null);
  }, [ppt, buildInjectCode]);

  // postMessage 助手
  const postToIframe = useCallback((msg: any) => {
    iframeRef.current?.contentWindow?.postMessage(msg, '*');
  }, []);

  // slide-ready 安全超时：如果注入脚本执行失败导致 slide-ready 永不抵达，
  // 5 秒后强制设为 ready + 消费缓存操作（降级模式，部分编辑功能仍可用）
  useEffect(() => {
    if (!htmlContent) return;
    const timer = setTimeout(() => {
      // 确认 iframe 仍然挂载
      if (!iframeRef.current?.contentDocument) return;
      setIframeReady(prev => {
        if (!prev) {
          console.warn('[PPT-EDIT] slide-ready timeout after 5s, force ready');
          // 消费缓存的待处理操作
          if (pendingPageRef.current !== null) {
            postToIframe({ type: 'sync-page', index: pendingPageRef.current });
            pendingPageRef.current = null;
          }
          if (pendingToggleRef.current !== null) {
            postToIframe({ type: 'toggle-edit', active: pendingToggleRef.current });
            pendingToggleRef.current = null;
          }
          return true;
        }
        return prev;
      });
    }, 5000);
    return () => clearTimeout(timer);
  }, [htmlContent, postToIframe]);

  // iframe 消息监听 + 父窗口驱动的拖拽处理（mousemove/mouseup 在 React 父窗口层）
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      const data = e.data || {};
      if (data.type === 'slide-ready') {
        setIframeReady(true);
        if (pendingPageRef.current !== null) {
          // 直接操作 iframe DOM 跳转到待定页面
          const iframeDoc = iframeRef.current?.contentDocument;
          if (iframeDoc) {
            const slides = iframeDoc.querySelectorAll('.ppt-slide');
            if (slides.length > 0 && pendingPageRef.current >= 0 && pendingPageRef.current < slides.length) {
              slides.forEach((s, i) => {
                const el = s as HTMLElement;
                el.classList.toggle('active', i === pendingPageRef.current);
                el.style.display = i === pendingPageRef.current ? 'flex' : 'none';
                el.style.opacity = i === pendingPageRef.current ? '1' : '0';
              });
            }
          }
          postToIframe({ type: 'go-to-page', index: pendingPageRef.current });
          pendingPageRef.current = null;
        }
        // 发送待处理的编辑模式切换
        if (pendingToggleRef.current !== null) {
          postToIframe({ type: 'toggle-edit', active: pendingToggleRef.current });
          pendingToggleRef.current = null;
        }
      }
      if (data.type === 'element-selected') {
        const p = data.pos || { x: 0, y: 0, w: 0, h: 0 };
        setSelectedElInfo({ tag: data.tag, text: data.text, x: p.x, y: p.y, w: p.w, h: p.h });
        setEditTextVal(data.text);
        setEditXVal(p.x);
        setEditYVal(p.y);
      }
      // 右键弹出编辑窗口
      if (data.type === 'element-contextmenu') {
        const p = data.pos || { x: 0, y: 0, w: 0, h: 0 };
        setSelectedElInfo({ tag: data.tag, text: data.text, x: p.x, y: p.y, w: p.w, h: p.h });
        setEditTextVal(data.text);
        setEditXVal(p.x);
        setEditYVal(p.y);
        setEditFontSize(data.fontSize || 16);
        // 弹出位置：靠近鼠标，但不要超出视口
        const mX = data.mouseX || 0;
        const mY = data.mouseY || 0;
        const popW = 280;
        const popH = 320;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        setPopupPos({
          x: Math.min(mX, vw - popW - 16),
          y: Math.min(mY, vh - popH - 16),
        });
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [postToIframe]);

  // 同步 ref 到最新 state 值供拖拽闭包使用
  useEffect(() => { selInfoRef.current = selectedElInfo; }, [selectedElInfo]);
  useEffect(() => { editTextValRef.current = editTextVal; }, [editTextVal]);
  useEffect(() => { editFontSizeRef.current = editFontSize; }, [editFontSize]);
  useEffect(() => { currentPageRef.current = currentPage; }, [currentPage]);

  // 当前页变化时直接操作 iframe DOM 切换到对应幻灯片 + 同步 postMessage
  useEffect(() => {
    if (!iframeReady) {
      pendingPageRef.current = currentPage;
      return;
    }
    // 直接操作 iframe 内的 DOM，避免 postMessage 注入脚本可能失败的情况
    const iframeDoc = iframeRef.current?.contentDocument;
    if (iframeDoc) {
      const slides = iframeDoc.querySelectorAll('.ppt-slide');
      if (slides.length > 0 && currentPage >= 0 && currentPage < slides.length) {
        slides.forEach((s, i) => {
          const el = s as HTMLElement;
          el.classList.toggle('active', i === currentPage);
          el.style.display = i === currentPage ? 'flex' : 'none';
          el.style.opacity = i === currentPage ? '1' : '0';
          // 清除 goToPage 动画残留的 transform/transition，防止幻灯片被推出视口
          el.style.transform = '';
          el.style.transition = '';
        });
      }
    }
    // 发送 sync-page 仅同步内部状态，不触发 goToPage 动画（避免 rAF 延迟回调覆盖当前 DOM）
    postToIframe({ type: 'sync-page', index: currentPage });
  }, [currentPage, iframeReady, postToIframe]);

  // 编辑模式切换
  useEffect(() => {
    if (!iframeReady) {
      // iframe 未就绪时缓存待发送的值
      pendingToggleRef.current = visualEditMode;
      return;
    }
    pendingToggleRef.current = null;
    postToIframe({ type: 'toggle-edit', active: visualEditMode });
    if (!visualEditMode) {
      setSelectedElInfo(null);
    }
  }, [visualEditMode, iframeReady, postToIframe]);

  // 加载已保存的视觉编辑（页面变化后重新应用）
  useEffect(() => {
    if (!iframeReady || !ppt?.pages_json) return;
    const pageKey = String(currentPage);
    const pageData = ppt.pages_json[currentPage];
    // editsMap 优先（当前会话修改），其次才是已保存数据
    const stored = editsMap[pageKey] || pageData?._visual_edits || null;
    if (stored && stored.length > 0) {
      // 延迟一帧确保 DOM 已渲染
      const timer = setTimeout(() => {
        postToIframe({ type: 'apply-stored', edits: stored });
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [currentPage, iframeReady, ppt, editsMap, postToIframe]);

  // 应用文本/字号修改到 iframe 并记录编辑
  const handleApplyEdit = useCallback(() => {
    if (!selectedElInfo) return;
    postToIframe({ type: 'update-element', text: editTextVal, fontSize: editFontSize });
    setSelectedElInfo(prev => prev ? { ...prev, text: editTextVal } : null);
    // 记录到 editsMap
    const pageKey = String(currentPage);
    setEditsMap(prev => {
      const pageEdits = (prev[pageKey] || []).filter(e => e.tag !== selectedElInfo.tag);
      return { ...prev, [pageKey]: [...pageEdits, { tag: selectedElInfo.tag, text: editTextVal, fontSize: editFontSize }] };
    });
    // 应用后关闭弹出
    setPopupPos(null);
  }, [selectedElInfo, editTextVal, editFontSize, currentPage, postToIframe]);

  const handleCancelEdit = useCallback(() => {
    setVisualEditMode(false);
    setSelectedElInfo(null);
    setPopupPos(null);
    postToIframe({ type: 'clear-selection' });
  }, [postToIframe]);

  // 保存视觉编辑到后端
  const handleSaveVisualEdit = useCallback(async () => {
    if (!ppt || !id) return;
    setSavingVisual(true);
    try {
      // 合并当前选中的元素到 editsMap（如果还没记录）
      if (selectedElInfo) {
        const pageKey = String(currentPage);
        setEditsMap(prev => {
          const pageEdits = (prev[pageKey] || []).filter(e => e.tag !== selectedElInfo.tag);
          return { ...prev, [pageKey]: [...pageEdits, { tag: selectedElInfo.tag, text: editTextVal, x: editXVal, y: editYVal, fontSize: editFontSize }] };
        });
      }
      // 先清除选择
      postToIframe({ type: 'clear-selection' });
      setVisualEditMode(false);
      setSelectedElInfo(null);
      setPopupPos(null);
      // 发送到后端
      if (Object.keys(editsMap).length > 0) {
        const allEdits = { ...editsMap };
        // 加入当前页正在编辑的改动
        if (selectedElInfo) {
          const pk = String(currentPage);
          const pageEdits = (allEdits[pk] || []).filter(e => e.tag !== selectedElInfo.tag);
          allEdits[pk] = [...pageEdits, { tag: selectedElInfo.tag, text: editTextVal, x: editXVal, y: editYVal, fontSize: editFontSize }];
        }
        await teacherApi.ppt.saveVisualEdits(id, { page_edits: allEdits });
      }
      // 重新加载 PPT 数据
      const updated = await teacherApi.ppt.get(id);
      setPpt(updated);
      setEditsMap({});
    } catch (e: any) {
      alert('保存失败: ' + e.message);
    } finally {
      setSavingVisual(false);
    }
  }, [ppt, id, currentPage, selectedElInfo, editTextVal, editXVal, editYVal, editsMap, postToIframe]);

  const pages = ppt?.pages_json || [];
  const page = pages[currentPage];

  const loadVersions = async () => {
    if (!ppt) return;
    try {
      const res = await teacherApi.ppt.listVersions(ppt.id, { page_size: 50 });
      setVersions(res.items);
      setShowVersions(true);
    } catch { setShowVersions(true); }
  };

  const handleThemeChange = async (themeName: string) => {
    if (!ppt) return;
    setChangingTheme(true);
    try {
      const updated = await teacherApi.ppt.retheme(ppt.id, themeName);
      setPpt(updated);
      setShowThemeMenu(false);
    } catch (e: any) {
      alert('切换主题失败: ' + e.message);
    } finally {
      setChangingTheme(false);
    }
  };

  const handleExport = async () => {
    if (!ppt) return;
    setExporting(true);
    try {
      const result = await teacherApi.ppt.export(ppt.id);
      const win = window.open('', '_blank');
      if (win) {
        win.document.write(result.html_content);
        win.document.close();
      } else {
        const blob = new Blob([result.html_content], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${result.title}.html`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      alert('导出失败: ' + e.message);
    } finally {
      setExporting(false);
    }
  };


  const handleRegenerate = async () => {
    if (!ppt || !page) return;
    setRegenerating(true);
    try {
      const result = await teacherApi.ppt.regeneratePage(ppt.id, {
        page_index: currentPage,
        outline_title: page.title || `第${currentPage + 1}页`,
        lesson_type: ppt.lesson_type,
        subject: ppt.subject,
        grade: ppt.grade,
      });
      if (result) {
        const newPages = [...pages];
        newPages[currentPage] = result.page;
        setPpt({ ...ppt, pages_json: newPages });
      }
    } catch (e: any) {
      alert('重新生成失败: ' + e.message);
    } finally {
      setRegenerating(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!ppt) return;
    try {
      const newPages = [...pages];
      newPages[currentPage] = { ...page, content: JSON.parse(editContent) };
      await teacherApi.ppt.update(ppt.id, { pages_json: newPages });
      const updated = await teacherApi.ppt.get(ppt.id);
      setPpt(updated);
      setEditMode(false);
    } catch (e: any) {
      alert('保存失败: ' + e.message);
    }
  };

  const handleStartClass = async () => {
    if (!ppt) return;
    try {
      console.log('[Edit] startClassroom pptId=', ppt.id);
      const session = await teacherApi.ppt.startClassroom(ppt.id);
      console.log('[Edit] startClassroom 返回 session=', session);
      if (!session?.id) {
        alert('启动课堂失败：未返回有效的课堂ID');
        return;
      }
      console.log('[Edit] 导航到 /ppt/present/' + session.id);
      navigate(`/ppt/present/${session.id}`);
    } catch (e: any) {
      console.error('[Edit] startClassroom 失败:', e);
      alert('启动课堂失败: ' + e.message);
    }
  };

  const handleRestoreVersion = async (version: PptVersionItem) => {
    if (!window.confirm(`确定恢复到版本 ${version.version}（${version.change_summary || '无备注'}）？当前版本将会被覆盖。`)) return;
    try {
      const detail = await teacherApi.ppt.getVersion(ppt!.id, version.id);
      await teacherApi.ppt.update(ppt!.id, {
        pages_json: detail.pages_json,
        theme_name: detail.theme_name,
      });
      const updated = await teacherApi.ppt.get(ppt!.id);
      setPpt(updated);
      setShowVersions(false);
    } catch (e: any) {
      alert('恢复版本失败: ' + e.message);
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', color: colors['text-tertiary'], fontSize: 15 }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ width: 32, height: 32, border: `3px solid ${colors['surface-soft']}`, borderTopColor: colors.success, borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
        加载中...
      </div>
    </div>
  );
  if (!ppt) return (
    <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>PPT 不存在</div>
  );

  const currentThemeName = ppt.theme_name || 'classic';

  return (
    <>
      <div style={{ display: 'flex', height: 'calc(100vh - 48px)', gap: space.sm }}>
      {/* 左侧缩略图列表 — 绿色主题 */}
      <div style={{
        width: 200, overflow: 'auto', flexShrink: 0,
        ...cardStyle, padding: space.sm, display: 'flex', flexDirection: 'column', gap: 2,
      }}>
        <div style={{
          ...typography.eyebrow, color: colors['text-tertiary'],
          padding: `0 ${space.xs}px ${space.xs}px`, letterSpacing: '0.5px',
        }}>
          页面列表 · {pages.length} 页
        </div>
        {pages.map((p: any, i: number) => (
          <div key={i} onClick={() => setCurrentPage(i)} style={{
            padding: `8px ${space.xs}px`, borderRadius: radius.sm, cursor: 'pointer',
            background: currentPage === i ? green.bg3 : 'transparent',
            borderLeft: currentPage === i ? `3px solid ${colors.success}` : '3px solid transparent',
            transition: 'all 0.15s',
          }}
            onMouseEnter={(e) => { if (currentPage !== i) e.currentTarget.style.background = colors['surface-soft']; }}
            onMouseLeave={(e) => { if (currentPage !== i) e.currentTarget.style.background = 'transparent'; }}
          >
            <div style={{
              fontWeight: currentPage === i ? 600 : 400,
              fontSize: 13, color: currentPage === i ? colors.success : colors['text-primary'],
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {p.title || `第${i + 1}页`}
            </div>
            <div style={{ fontSize: 11, color: colors['text-tertiary'], marginTop: 1 }}>
              {SLIDE_TYPE_LABELS[p.type] || p.type}
            </div>
          </div>
        ))}
      </div>

      {/* 中间内容区 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: space.sm, minWidth: 0 }}>
        {/* 顶栏工具栏 */}
        <div style={{
          ...cardStyle, padding: `${space.sm}px ${space.md}px`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: space.xs,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            <span style={{ ...typography.subhead, fontWeight: 600, color: colors['text-primary'] }}>
              {ppt.title}
            </span>
            <span style={{ ...typography['body-sm'], color: colors['text-tertiary'] }}>
              {currentPage + 1} / {pages.length}
            </span>
            {/* 当前主题标签 */}
            <span style={{
              padding: '2px 10px', borderRadius: radius.pill, fontSize: 12, fontWeight: 500,
              background: green.bg3, color: colors.success,
            }}>
              {THEME_NAMES[currentThemeName] || currentThemeName}
            </span>
            <span style={{ ...typography.caption, color: colors['text-tertiary'] }}>v{ppt.version}</span>
          </div>

          <div style={{ display: 'flex', gap: space.xs, flexWrap: 'wrap' }}>
            {/* 主题切换 */}
            <div style={{ position: 'relative' }}>
              <button onClick={() => setShowThemeMenu(!showThemeMenu)}
                style={{ ...btnSmall, background: green.bg3, color: colors.success, border: `1px solid ${colors.success}30` }}>
                主题
              </button>
              {showThemeMenu && (
                <div style={{
                  position: 'absolute', top: '100%', right: 0, marginTop: 4, zIndex: 100,
                  ...cardStyle, padding: space.xs, minWidth: 200, maxHeight: 320, overflow: 'auto',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
                }}>
                  {themes.map((t) => (
                    <div key={t.id} onClick={() => handleThemeChange(t.name)} style={{
                      padding: `8px ${space.sm}px`, borderRadius: radius.sm, cursor: 'pointer',
                      background: t.name === currentThemeName ? green.bg3 : 'transparent',
                      color: t.name === currentThemeName ? colors.success : colors['text-primary'],
                      fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, transition: 'background 0.1s',
                    }}
                      onMouseEnter={(e) => { if (t.name !== currentThemeName) e.currentTarget.style.background = colors['surface-soft']; }}
                      onMouseLeave={(e) => { if (t.name !== currentThemeName) e.currentTarget.style.background = 'transparent'; }}
                    >
                      <span style={{ width: 14, height: 14, borderRadius: '50%', background: t.preview_color || colors['text-tertiary'], display: 'inline-block', flexShrink: 0 }} />
                      <span style={{ fontWeight: t.name === currentThemeName ? 600 : 400, flex: 1 }}>{t.display_name}</span>
                      {t.name === currentThemeName && <IconCheck size={14} color={colors.success} />}
                    </div>
                  ))}
                  {changingTheme && <div style={{ padding: space.xs, color: colors['text-tertiary'], fontSize: 12 }}>切换中...</div>}
                </div>
              )}
            </div>

            {/* 版本历史 */}
            <button onClick={loadVersions}
              style={{ ...btnSmallSecondary }}>
              版本
            </button>

            {/* HTML 导出 */}
            <button onClick={handleExport} disabled={exporting}
              style={{ ...btnSmallSecondary, opacity: exporting ? 0.6 : 1 }}>
              {exporting ? '导出中...' : 'HTML 导出'}
            </button>



            <button onClick={() => navigate('/ppt')} style={btnSmallSecondary}>
              ← 返回
            </button>
            <button onClick={handleStartClass}
              style={{ ...btnSmall, background: colors.success, color: '#fff', border: 'none', fontWeight: 600, gap: 4 }}>
              <IconPlay size={14} color="#fff" /> 授课
            </button>
          </div>
        </div>

        {/* 版本历史弹窗 */}
        {showVersions && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: colors.overlay, display: 'flex', justifyContent: 'center',
            alignItems: 'center', zIndex: 200,
          }} onClick={() => setShowVersions(false)}>
            <div onClick={(e) => e.stopPropagation()} style={{
              ...cardStyle, padding: space.lg, minWidth: 420, maxWidth: 600,
              maxHeight: '80vh', overflow: 'auto',
            }}>
              <div style={{ ...typography['card-title'], marginBottom: space.md }}>版本历史</div>
              {versions.length === 0 ? (
                <div style={{ color: colors['text-tertiary'], ...typography['body-sm'] }}>暂无版本记录</div>
              ) : (
                versions.map((v) => (
                  <div key={v.id} style={{
                    padding: `10px ${space.sm}px`, marginBottom: space.xs, borderRadius: radius.md,
                    background: colors['surface-soft'], border: `1px solid ${colors.hairline}`,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14, color: colors['text-primary'] }}>v{v.version}</div>
                      <div style={{ ...typography['body-sm'], color: colors['text-secondary'], marginTop: 2 }}>
                        {v.change_summary || '无备注'} · {new Date(v.created_at).toLocaleString()}
                      </div>
                    </div>
                    <button onClick={() => handleRestoreVersion(v)}
                      style={{ ...btnSmall, background: green.bg, color: colors.success, border: 'none' }}>
                      恢复
                    </button>
                  </div>
                ))
              )}
              <div style={{ textAlign: 'right', marginTop: space.sm }}>
                <button onClick={() => setShowVersions(false)} style={btnSecondary}>
                  关闭
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 页面预览 */}
        {page && (
          <div style={{
            flex: 1, ...cardStyle, padding: space.lg, overflow: 'auto',
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{
              marginBottom: space.md, display: 'flex', justifyContent: 'space-between',
              alignItems: 'flex-start', gap: space.sm,
            }}>
              <div>
                <h3 style={{ margin: 0, ...typography.headline, color: colors['text-primary'] }}>
                  {page.title}
                </h3>
                <span style={{ ...typography['body-sm'], color: colors['text-tertiary'] }}>
                  {SLIDE_TYPE_LABELS[page.type] || page.type}
                </span>
              </div>
              <div style={{ display: 'flex', gap: space.xs, flexShrink: 0 }}>
                <button onClick={handleRegenerate} disabled={regenerating}
                  style={{
                    ...btnSmall, gap: 4,
                    background: green.bg, color: colors.success, border: `1px solid ${colors.success}30`,
                    opacity: regenerating ? 0.6 : 1,
                  }}>
                  <IconRefresh size={12} color={colors.success} />
                  {regenerating ? '生成中...' : 'AI 重新生成'}
                </button>
                {(() => {
                  // 编辑模式已开启 → 显示保存/退出按钮
                  if (visualEditMode) return (
                    <>
                      <button onClick={handleSaveVisualEdit} disabled={savingVisual}
                        style={{
                          ...btnSmall, background: colors.success, color: '#fff',
                          border: 'none', fontWeight: 600, opacity: savingVisual ? 0.6 : 1,
                        }}>
                        {savingVisual ? '保存中...' : '保存'}
                      </button>
                      <button onClick={() => setVisualEditMode(false)}
                        style={{ ...btnSmallSecondary }}>
                        退出编辑
                      </button>
                    </>
                  );
                  // 无 HTML 内容 → 不显示编辑按钮（没有 iframe 可以编辑）
                  if (!htmlContent) return null;
                  // iframe 仍在加载中 → 显示禁用状态
                  if (!iframeReady) return (
                    <button disabled
                      style={{
                        ...btnSmall,
                        background: '#f5f5f5',
                        color: colors['text-tertiary'],
                        border: `1px solid ${colors.hairline}`,
                        cursor: 'not-allowed',
                      }}>
                      <IconEdit size={12} color={colors['text-tertiary']} />
                      加载中...
                    </button>
                  );
                  // 正常可编辑状态
                  return (
                    <button onClick={() => setVisualEditMode(true)}
                      style={{
                        ...btnSmall,
                        background: green.bg,
                        color: colors.success,
                        border: `1px solid ${colors.success}30`,
                      }}>
                      <IconEdit size={12} color={colors['text-secondary']} />
                      编辑
                    </button>
                  );
                })()}
              </div>
            </div>

            {/* 内容展示区域 — 始终显示 iframe 预览 */}
            <div style={{
              flex: 1, padding: 0, background: '#fff',
              border: `1px solid ${colors.hairline}`, borderRadius: radius.md,
              overflow: 'hidden', position: 'relative',
            }}>
              {htmlContent ? (
                <iframe
                  ref={iframeRef}
                  srcDoc={htmlContent}
                  title="PPT Preview"
                  style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
                  sandbox="allow-scripts allow-same-origin"
                />
              ) : (
                <div style={{ padding: 40, textAlign: 'center', color: colors['text-tertiary'] }}>
                  暂无 HTML 渲染内容
                </div>
              )}

              {/* 可视化编辑 — 右键弹出编辑窗口 */}
              {visualEditMode && selectedElInfo && popupPos && (
                <div style={{
                    position: 'fixed', left: popupPos.x, top: popupPos.y, width: 270,
                    background: '#fff',
                    borderRadius: radius.lg,
                    boxShadow: '0 8px 32px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.06)',
                    padding: space.md, zIndex: 20,
                    display: 'flex', flexDirection: 'column', gap: space.xs,
                  }}>
                    {/* 标题栏 */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, color: colors['text-primary'], fontFamily: 'monospace' }}>
                        &lt;{selectedElInfo.tag}&gt;
                      </span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: 11, color: colors['text-tertiary'] }}>
                          {selectedElInfo.w}×{selectedElInfo.h}
                        </span>
                        <button onClick={() => { setPopupPos(null); postToIframe({ type: 'clear-selection' }); setSelectedElInfo(null); }}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, lineHeight: 1, fontSize: 16, color: colors['text-tertiary'] }}>
                          ✕
                        </button>
                      </div>
                    </div>

                    {/* 提示 */}
                    <div style={{ fontSize: 11, color: '#999', padding: '2px 0', lineHeight: 1.3 }}>
                      点击选中元素 · 右键弹出本窗口
                    </div>

                    {/* 文字内容 */}
                    <label style={{ fontSize: 12, fontWeight: 500, color: colors['text-secondary'] }}>文字内容</label>
                    <input value={editTextVal}
                      onChange={e => setEditTextVal(e.target.value)}
                      style={{
                        width: '100%', padding: '6px 10px', fontSize: 13,
                        border: `1px solid ${colors.hairline}`, borderRadius: radius.sm,
                        outline: 'none', boxSizing: 'border-box',
                      }} />

                    {/* 字号 */}
                    <label style={{ fontSize: 12, fontWeight: 500, color: colors['text-secondary'] }}>字号 (px)</label>
                    <input type="number" value={editFontSize} min={8} max={200}
                      onChange={e => setEditFontSize(Number(e.target.value) || 16)}
                      style={{
                        width: '100%', padding: '6px 10px', fontSize: 13,
                        border: `1px solid ${colors.hairline}`, borderRadius: radius.sm,
                        outline: 'none', boxSizing: 'border-box',
                      }} />

                    {/* 按钮 */}
                    <div style={{ display: 'flex', gap: space.xs, marginTop: 4 }}>
                      <button onClick={handleApplyEdit}
                        style={{
                          flex: 1, ...btnSmall, background: colors.success, color: '#fff',
                          border: 'none', fontSize: 12,
                        }}>
                        应用
                      </button>
                      <button onClick={() => { setPopupPos(null); postToIframe({ type: 'clear-selection' }); setSelectedElInfo(null); }}
                        style={{ ...btnSmallSecondary, fontSize: 12 }}>
                        关闭
                      </button>
                    </div>
                  </div>
                )}
            </div>

            {/* 音频文字展开按钮 */}
            {(page.type === 'listening' || page.type === 'speaking') && (
              <div style={{ marginTop: space.md }}>
                <button onClick={() => setShowAudioText(!showAudioText)}
                  style={{ ...btnSmallSecondary, color: colors.success, borderColor: `${colors.success}30` }}>
                  {showAudioText ? '收起音频文字' : '查看音频文字'}
                </button>
                {showAudioText && (
                  <div style={{
                    marginTop: space.xs, padding: space.sm, background: colors['surface-soft'],
                    borderRadius: radius.md, fontSize: 14, lineHeight: 1.8,
                    whiteSpace: 'pre-wrap', color: colors['text-primary'],
                  }}>
                    {page.content?.audio_text || page.content?.text || ''}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 底部翻页导航 */}
        <div style={{
          display: 'flex', justifyContent: 'center', alignItems: 'center', gap: space.sm,
          padding: `${space.xs}px 0`,
        }}>
          <button onClick={() => setCurrentPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0}
            style={{
              ...btnSmallSecondary, display: 'flex', alignItems: 'center', gap: 4,
              opacity: currentPage === 0 ? 0.4 : 1, cursor: currentPage === 0 ? 'not-allowed' : 'pointer',
            }}>
            <IconBack size={12} color={colors['text-secondary']} /> 上一页
          </button>

          {/* 页码按钮组 */}
          <div style={{ display: 'flex', gap: 4 }}>
            {pages.map((_: any, i: number) => (
              <button key={i} onClick={() => setCurrentPage(i)} style={{
                width: 28, height: 28, borderRadius: '50%', border: 'none',
                background: currentPage === i ? colors.success : colors['surface-soft'],
                color: currentPage === i ? '#fff' : colors['text-secondary'],
                fontSize: 11, fontWeight: currentPage === i ? 600 : 400,
                cursor: 'pointer', transition: 'all 0.15s',
              }}>
                {i + 1}
              </button>
            ))}
          </div>

          <button onClick={() => setCurrentPage(Math.min(pages.length - 1, currentPage + 1))} disabled={currentPage >= pages.length - 1}
            style={{
              ...btnSmallSecondary, display: 'flex', alignItems: 'center', gap: 4,
              opacity: currentPage >= pages.length - 1 ? 0.4 : 1,
              cursor: currentPage >= pages.length - 1 ? 'not-allowed' : 'pointer',
            }}>
            下一页 <IconArrowRight size={12} color={colors['text-secondary']} />
          </button>
        </div>
      </div>
      </div>

      {/* SVG 在线编辑器 */}
      {showEditor && id && (
        <SVGEditor
          pptId={id}
          initialSlideCount={ppt?.slide_count || ppt?.pages_json?.length || 1}
          onClose={() => {
            setShowEditor(false);
            // 重载 PPT 数据以反映可能的修改
            if (id) teacherApi.ppt.get(id).then(setPpt).catch(() => {});
          }}
          onSaved={() => {
            if (id) teacherApi.ppt.get(id).then(setPpt).catch(() => {});
          }}
        />
      )}
    </>
  );
}
