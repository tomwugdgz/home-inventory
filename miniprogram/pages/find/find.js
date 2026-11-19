const app = getApp();
const api = require('../../utils/api.js');
const CAT_ICON = { '衣物':'👕','工具':'🔧','食品':'🍫','日用':'🧴','数码':'🔌','书籍':'📚','其他':'📦' };

Page({
  data: { keyword:'', allItems:[], results:[], detail:null, showLocPicker:false, allLocs:[], rawItems:[] },

  onLoad(opt) {
    this.load(() => { if (opt.id) this.openById(opt.id); });
  },
  onShow() {
    // 首页物品卡片点进来时，用 globalData 传 id（tabBar 页不能 navigateTo 带 query）
    const pid = app.globalData.pendingItemId;
    if (pid) {
      app.globalData.pendingItemId = '';
      this.load(() => this.openById(pid));
    } else if (!this.data.detail) this.load();
  },

  load(cb) {
    app.refreshBootstrap().then(bs => {
      const now = Date.now();
      const raw = bs.items || [];
      const items = raw.map(i => {
        const h = Math.floor((now - i.created_at)/3600000);
        return { ...i, icon: CAT_ICON[i.category]||'📦',
          locName: app.fullLoc(i.location_id),
          timeAgo: h<1?'刚刚':(h<24?h+'小时前':Math.floor(h/24)+'天前') };
      });
      this.setData({ rawItems: raw, allItems: items, results: items, allLocs: bs.locations||[] }, cb);
    }).catch(e => wx.showToast({ icon:'none', title:'加载失败' }));
  },

  onInput(e) { this.setData({ keyword: e.detail.value }, () => this.filter()); },
  clear() { this.setData({ keyword:'' }, () => this.filter()); },
  filter() {
    const q = this.data.keyword.trim().toLowerCase();
    if (!q) return this.setData({ results: this.data.allItems });
    const r = this.data.allItems.filter(i =>
      (i.name + (i.category||'') + (i.use_scene||'') + (i.color||'') + i.locName + (i.tags||[]).join('')).toLowerCase().includes(q)
    );
    this.setData({ results: r });
  },

  openById(id) {
    const it = this.data.allItems.find(i => i.id === id);
    if (it) this.setData({ detail: it });
  },
  showItem(e) { this.openById(e.currentTarget.dataset.id); },
  closeDetail() { this.setData({ detail:null, showLocPicker:false }); },
  noop() {},

  editLoc() { this.setData({ showLocPicker:true }); },
  closeLocPicker() { this.setData({ showLocPicker:false }); },
  pickLoc(e) {
    const lid = e.currentTarget.dataset.id;
    const d = this.data.detail;
    if (!d) return;
    api.updateItem(d.id, { location_id: lid }).then(() => {
      this.setData({ showLocPicker:false });
      wx.showToast({ title:'已移动' });
      this.load(() => this.openById(d.id));
    }).catch(err => wx.showToast({ icon:'none', title:err.error||'失败' }));
  },

  deleteItem() {
    const d = this.data.detail;
    if (!d) return;
    wx.showModal({ title:'删除物品', content:'确定删除「'+d.name+'」？', success:r => {
      if (!r.confirm) return;
      api.deleteItem(d.id).then(() => {
        this.setData({ detail:null }); wx.showToast({ title:'已删除' }); this.load();
      });
    }});
  },
});
