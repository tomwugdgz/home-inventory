// 家物志小程序 · 全局逻辑
App({
  globalData: {
    // 全量数据缓存（登录后一次拉取）
    bootstrap: null,
    apiBase: require('./config.js').API_BASE,
  },

  onLaunch() {
    console.log('家物志启动，后端地址:', this.globalData.apiBase);
  },

  // 拉取全量数据（各页面 onShow 调用，保证数据最新）
  refreshBootstrap() {
    const api = require('./utils/api.js');
    return api.bootstrap().then(data => {
      this.globalData.bootstrap = data;
      return data;
    });
  },

  // 工具：根据位置 id 拿完整路径
  fullLoc(id) {
    const bs = this.globalData.bootstrap;
    if (!bs || !id) return '未分类';
    const locs = bs.locations || [];
    const find = (lid) => locs.find(l => l.id === lid);
    const l = find(id);
    if (!l) return '未分类';
    return l.parent_id ? (find(l.parent_id)?.name || '') + ' · ' + l.name : l.name;
  },
});
