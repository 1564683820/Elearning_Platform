const api = require('../../../utils/api.js');
const { markdownToHtml } = require('../../../utils/markdown.js');

Page({
  data: {
    report: { title: '', content: '', created_at: '', exam_name: '' },
    reportNodes: [],
    loading: true,
    rawContent: '',
  },

  onLoad(options) {
    const reportId = options.reportId;
    if (reportId) {
      this.loadReport(reportId);
    } else {
      this.setData({ loading: false });
      wx.showToast({ title: '参数错误', icon: 'none' });
    }
  },

  async loadReport(reportId) {
    try {
      console.log('[报告详情] 开始加载 reportId:', reportId);
      const res = await api.getSummaryReportDetail(reportId);
      console.log('[报告详情] API 返回:', res ? `title="${res.title}" content长度=${(res.content||'').length}` : '空');
      if (res && res.content) {
        // 将 Markdown 转为 HTML nodes 供 rich-text 渲染
        const rawContent = res.content;
        console.log('[报告详情] 原始内容前200字:', rawContent.substring(0, 200));
        console.log('[报告详情] 原始内容是否含#标记:', /#/.test(rawContent));
        const html = markdownToHtml(rawContent);
        console.log('[报告详情] 转换后 HTML 前200字:', html.substring(0, 200));
        console.log('[报告详情] 转换后含#标记:', /#[^#]/.test(html.replace(/#[0-9A-Fa-f]{3,6}/g, '')));
        this.setData({
          report: res,
          reportNodes: html,
          rawContent,
          loading: false,
        });
      } else if (res) {
        this.setData({ report: res, reportNodes: '', rawContent: '', loading: false });
        wx.showToast({ title: '报告内容为空', icon: 'none' });
      } else {
        this.setData({ loading: false });
        wx.showToast({ title: '报告不存在', icon: 'none' });
      }
    } catch (err) {
      console.error('[报告详情] 加载报告失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onCopyReport() {
    wx.setClipboardData({
      data: this.data.rawContent || this.data.report.content,
      success() {
        wx.showToast({ title: '已复制', icon: 'success' });
      },
    });
  },

  // ======== 导出为长图 ========

  async onExportImage() {
    const { report, rawContent } = this.data;
    if (!rawContent) {
      wx.showToast({ title: '无内容可导出', icon: 'none' });
      return;
    }

    // 检查相册权限
    try {
      const authSetting = await wx.getSetting();
      if (!authSetting.authSetting['scope.writePhotosAlbum']) {
        const authRes = await wx.authorize({ scope: 'scope.writePhotosAlbum' });
        console.log('[导出长图] 授权结果:', authRes);
      }
    } catch (err) {
      // 用户拒绝授权，引导手动开启
      console.warn('[导出长图] 相册权限未授予', err);
      wx.showModal({
        title: '需要相册权限',
        content: '导出长图需要保存到相册，请在设置中开启权限',
        success(res) {
          if (res.confirm) {
            wx.openSetting();
          }
        },
      });
      return;
    }

    wx.showLoading({ title: '生成长图中...', mask: true });

    try {
      const tempFilePath = await this._renderLongImage(report, rawContent);
      wx.hideLoading();

      // 保存到相册（Promise 包装回调 API）
      await new Promise((resolve, reject) => {
        wx.saveImageToPhotosAlbum({
          filePath: tempFilePath,
          success: resolve,
          fail: reject,
        });
      });
      wx.showToast({ title: '已保存到相册', icon: 'success' });

      // 预览图片（用户可长按转发/保存）
      wx.previewImage({
        urls: [tempFilePath],
        showmenu: true,
      });
    } catch (err) {
      wx.hideLoading();
      console.error('[导出长图] 失败', err);
      wx.showToast({ title: '导出失败: ' + (err.errMsg || err.message || '未知错误'), icon: 'none' });
    }
  },

  /** 在 Canvas 上渲染报告内容，返回临时图片路径 */
  _renderLongImage(report, markdownContent) {
    return new Promise((resolve, reject) => {
      const query = wx.createSelectorQuery();
      query.select('#exportCanvas')
        .fields({ node: true, size: true })
        .exec((res) => {
          const canvas = res[0]?.node;
          if (!canvas) {
            reject(new Error('Canvas 节点不存在'));
            return;
          }

          const sysInfo = wx.getSystemInfoSync();
          const dpr = sysInfo.pixelRatio;
          const pageWidth = 375; // CSS 逻辑像素宽度（对应 750rpx）
          const physicalW = Math.round(pageWidth * dpr);  // 实际绘制像素宽
          const margin = 16 * dpr;
          const maxW = physicalW - margin * 2;            // 内容绘制宽度
          const baseSize = 14 * dpr;                       // 正文字体大小
          const lineH = Math.round(baseSize * 1.8);        // 行高

          const ctx = canvas.getContext('2d');

          // ---------- 辅助函数 ----------
          const wrapText = (text, maxWidth) => {
            const lines = [];
            let cur = '';
            for (const ch of text) {
              const test = cur + ch;
              if (ctx.measureText(test).width > maxWidth && cur) {
                lines.push(cur);
                cur = ch;
              } else {
                cur = test;
              }
            }
            if (cur) lines.push(cur);
            return lines;
          };

          // 渲染单行文本（剥离所有 Markdown 标记，折行回左边缘）
          const drawFormattedLine = (text, y, fontSize, color) => {
            const clean = text
              .replace(/\*\*(.+?)\*\*/g, '$1')
              .replace(/\*(.+?)\*/g, '$1')
              .replace(/~~(.+?)~~/g, '$1')
              .replace(/`([^`]+)`/g, '$1')
              .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
              .replace(/\|/g, '');
            ctx.font = fontSize + 'px sans-serif';
            ctx.fillStyle = color || '#374151';
            const lines = wrapText(clean, maxW);
            lines.forEach((ln, i) => ctx.fillText(ln, margin, y + i * lineH));
            return y + lines.length * lineH;
          };

          // 清理一行文本中残留的 Markdown 标记
          const cleanMarkdown = (text) => {
            return text
              .replace(/\*\*(.+?)\*\*/g, '$1')
              .replace(/\*(.+?)\*/g, '$1')
              .replace(/~~(.+?)~~/g, '$1')
              .replace(/`([^`]+)`/g, '$1')
              .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
              .replace(/\|/g, '')
              .replace(/\*+/g, '');
          };

          // ---------- 绘制内容 ----------
          // 计算总高度
          let totalH = margin;

          // 标题行
          const titleLines = report.title
            ? wrapText(report.title, maxW)
            : [];
          totalH += titleLines.length * (24 * dpr) + 6 * dpr;
          totalH += 4 * dpr; // 日期行

          // 正文行
          const bodyLines = markdownContent.split('\n');
          for (const ln of bodyLines) {
            const s = ln.trim();
            if (!s) {
              totalH += 8 * dpr;
              continue;
            }
            const sClean = cleanMarkdown(s);
            if (s.startsWith('#### ')) {
              totalH += lineH + 2 * dpr; // 4级标题
            } else if (s.startsWith('### ')) {
              totalH += lineH + 4 * dpr;
            } else if (s.startsWith('## ')) {
              totalH += lineH + 6 * dpr;
            } else if (s.startsWith('# ')) {
              totalH += lineH + 8 * dpr;
            } else if (/^---+\s*$/.test(s)) {
              totalH += 12 * dpr;
            } else if (/^\|/.test(s)) {
              // 表格行：清理后按正文计算高度
              ctx.font = baseSize + 'px sans-serif';
              const w = wrapText(sClean, maxW);
              totalH += w.length * lineH;
            } else {
              ctx.font = baseSize + 'px sans-serif';
              const w = wrapText(sClean, maxW);
              totalH += w.length * lineH;
            }
          }
          totalH += margin + 40 * dpr; // 底部安全缓冲区

          // 设置画布尺寸
          const physicalH = Math.ceil(totalH);
          canvas.width = physicalW;
          canvas.height = physicalH;

          // 绘制白色背景
          ctx.fillStyle = '#FFFFFF';
          ctx.fillRect(0, 0, physicalW, physicalH);

          let y = margin;

          // --- 标题 ---
          if (report.title) {
            ctx.font = 'bold ' + (20 * dpr) + 'px sans-serif';
            ctx.fillStyle = '#1F2937';
            const tLines = wrapText(report.title, maxW);
            tLines.forEach(ln => {
              ctx.fillText(ln, margin, y + 20 * dpr);
              y += 24 * dpr;
            });
            y += 2 * dpr;

            // 日期
            ctx.font = (12 * dpr) + 'px sans-serif';
            ctx.fillStyle = '#9CA3AF';
            ctx.fillText(report.created_at || '', margin, y);
            y += 18 * dpr;

            // 分割线
            y += 6 * dpr;
            ctx.strokeStyle = '#E5E7EB';
            ctx.lineWidth = 1 * dpr;
            ctx.beginPath();
            ctx.moveTo(margin, y);
            ctx.lineTo(physicalW - margin, y);
            ctx.stroke();
            y += 12 * dpr;
          }

          // --- 正文 ---
          for (const ln of bodyLines) {
            const s = ln.trim();
            if (!s) {
              y += 8 * dpr;
              continue;
            }

            try {
              if (s.startsWith('#### ')) {
                const text = cleanMarkdown(s.replace(/^####\s+/, ''));
                ctx.font = 'bold ' + (14 * dpr) + 'px sans-serif';
                ctx.fillStyle = '#374151';
                const lines = wrapText(text, maxW);
                lines.forEach((l, i) => ctx.fillText(l, margin, y + i * lineH));
                y += lines.length * lineH + 2 * dpr;

              } else if (s.startsWith('### ')) {
                const text = cleanMarkdown(s.replace(/^###\s+/, '').replace(/\s*#+\s*$/, '').trim());
                ctx.font = 'bold ' + (15 * dpr) + 'px sans-serif';
                ctx.fillStyle = '#1F2937';
                const lines = wrapText(text, maxW);
                lines.forEach((l, i) => ctx.fillText(l, margin, y + i * lineH));
                y += lines.length * lineH + 4 * dpr;

              } else if (s.startsWith('## ')) {
                const text = cleanMarkdown(s.replace(/^##\s+/, '').replace(/\s*#+\s*$/, '').trim());
                ctx.font = 'bold ' + (17 * dpr) + 'px sans-serif';
                ctx.fillStyle = '#1F2937';
                const lines = wrapText(text, maxW);
                lines.forEach((l, i) => ctx.fillText(l, margin, y + i * lineH));
                y += lines.length * lineH + 6 * dpr;

              } else if (s.startsWith('# ')) {
                const text = cleanMarkdown(s.replace(/^#\s+/, '').replace(/\s*#+\s*$/, '').trim());
                ctx.font = 'bold ' + (19 * dpr) + 'px sans-serif';
                ctx.fillStyle = '#1F2937';
                const lines = wrapText(text, maxW);
                lines.forEach((l, i) => ctx.fillText(l, margin, y + i * lineH));
                y += lines.length * lineH + 8 * dpr;

              } else if (/^---+\s*$/.test(s)) {
                y += 4 * dpr;
                ctx.strokeStyle = '#E5E7EB';
                ctx.lineWidth = 1 * dpr;
                ctx.beginPath();
                ctx.moveTo(margin, y);
                ctx.lineTo(physicalW - margin, y);
                ctx.stroke();
                y += 8 * dpr;

              } else if (/^> /.test(s)) {
                const text = s.replace(/^>\s+/, '');
                // 绿色竖线
                ctx.fillStyle = '#5B9E6F';
                ctx.fillRect(margin, y - 10 * dpr, 3 * dpr, lineH);
                const drawY = drawFormattedLine(text, y, baseSize, '#4B5563');
                y = drawY;
                y += 2 * dpr;

              } else if (/^[-*]\s/.test(s)) {
                const text = cleanMarkdown(s.replace(/^[-*]\s+/, ''));
                ctx.font = baseSize + 'px sans-serif';
                ctx.fillStyle = '#374151';
                // 圆点
                ctx.beginPath();
                ctx.arc(margin + 5 * dpr, y - 4 * dpr, 3 * dpr, 0, Math.PI * 2);
                ctx.fill();
                const lines = wrapText(text, maxW - 16 * dpr);
                lines.forEach((l, i) => {
                  ctx.fillText(l, margin + 16 * dpr, y + i * lineH);
                });
                y += lines.length * lineH;

              } else if (/^\d+\.\s/.test(s)) {
                const num = s.match(/^(\d+)\.\s*/)[1];
                const text = cleanMarkdown(s.replace(/^\d+\.\s+/, ''));
                ctx.font = baseSize + 'px sans-serif';
                ctx.fillStyle = '#374151';
                ctx.fillText(num + '.', margin, y);
                const lines = wrapText(text, maxW - 20 * dpr);
                lines.forEach((l, i) => {
                  ctx.fillText(l, margin + 20 * dpr, y + i * lineH);
                });
                y += lines.length * lineH;

              } else if (/^\|/.test(s)) {
                // 表格行：剥离管道符，按正文渲染
                y = drawFormattedLine(s, y, baseSize, '#374151');

              } else {
                // 普通段落（支持 **bold** 等标记）
                y = drawFormattedLine(s, y, baseSize, '#374151');
              }
            } catch (lineErr) {
              console.warn('[导出长图] 渲染行失败:', s.slice(0, 40), lineErr);
              y += lineH;
            }
          }

          // 底部水印
          y += 12 * dpr;
          ctx.font = (10 * dpr) + 'px sans-serif';
          ctx.fillStyle = '#D1D5DB';
          ctx.fillText('小e英语学习助手', physicalW - margin - ctx.measureText('小e英语学习助手').width, y);

          // 导出为图片
          wx.canvasToTempFilePath({
            canvas,
            fileType: 'png',
            quality: 1,
            success: (res) => resolve(res.tempFilePath),
            fail: (err) => reject(err),
          });
        });
    });
  },
});
