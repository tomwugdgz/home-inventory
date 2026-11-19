const app = getApp();
const api = require('../../utils/api.js');

const CAT_ICON = { '衣物':'👕','工具':'🔧','食品':'🍫','日用':'🧴','数码':'🔌','书籍':'📚','其他':'📦' };
const COLOR_HEX = { '黑':'#1D1D1F','白':'#FFFFFF','灰':'#8E8E93','红':'#E24B4A','蓝':'#378ADD','绿':'#639922','黄':'#EF9F27','米':'#E8DCC8','粉':'#ED93B1','棕':'#8B5E3C' };

Page({
  data: { items: [], recent: [], locations: [], member: {}, weekCount: 0, error: '' },

  onShow() { this.load(); },

  load() {
    this.setData({ error: '' });
    app.refreshBootstrap().then(bs => {
      const now = Date.now();
      let week = 0;
      const items = (bs.items || []).map(i => {
        if (now - i.created_at < 7 * 86400000) week++;
        const h = Math.floor((now - i.created_at) / 3600000);
        return {
          ...i,
          icon: CAT_ICON[i.category] || '📦',
          locName: app.fullLoc(i.location_id),
          timeAgo: h < 1 ? '刚刚' : (h < 24 ? h + '小时前' : Math.floor(h/24) + '天前'),
          colorDot: i.color && i.color !== '白' ? '● ' : '',
        };
      });
      this.setData({
        items,
        recent: items.slice(0, 5),
        locations: bs.locations || [],
        member: bs.member || {},
        weekCount: week,
      });
    }).catch(e => this.setData({ error: e.error || '加载失败' }));
  },

  goCapture() { app.globalData.captureMode = ''; wx.switchTab({ url: '/pages/capture/capture' }); },
  goCaptureNfc() {
    // switchTab 不支持带 query 参数，改用 globalData 传递目标模式
    app.globalData.captureMode = 'nfc';
    wx.switchTab({ url: '/pages/capture/capture' });
  },
  goFind() { wx.switchTab({ url: '/pages/find/find' }); },
  goMe() { wx.switchTab({ url: '/pages/me/me' }); },
  showItem(e) {
    // find 是 tabBar 页，navigateTo 无法跳转且不能带 query，用 globalData 中转
    app.globalData.pendingItemId = e.currentTarget.dataset.id;
    wx.switchTab({ url: '/pages/find/find' });
  },
});
