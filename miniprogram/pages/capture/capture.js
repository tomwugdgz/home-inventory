const app = getApp();
const api = require('../../utils/api.js');

const COLORS = [
  {n:'黑',c:'#1D1D1F'},{n:'白',c:'#FFFFFF'},{n:'灰',c:'#8E8E93'},{n:'红',c:'#E24B4A'},{n:'蓝',c:'#378ADD'},
  {n:'绿',c:'#639922'},{n:'黄',c:'#EF9F27'},{n:'米',c:'#E8DCC8'},{n:'粉',c:'#ED93B1'},{n:'棕',c:'#8B5E3C'},
];

Page({
  data: {
    mode:'cam', imagePath:'', base64:'', scanning:false, showForm:false,
    cats:[], uses:[], locNames:[], locIds:[], locIndex:0, useIndex:0,
    colors: COLORS,
    form:{ name:'', category:'其他', color:'米', use_scene:'其他', location_id:'' },
    aiResult:null, nfcResult:null, member:{}, error:'',
  },

  onLoad(opt) { if (opt.mode === 'nfc') this.setData({ mode:'nfc' }); },
  onShow() {
    // 首页「NFC 感应」经 switchTab 跳来，模式存在 globalData 中（switchTab 不支持 query）
    if (app.globalData.captureMode === 'nfc') {
      this.setData({ mode: 'nfc' });
      app.globalData.captureMode = '';
    }
    app.refreshBootstrap().then(bs => {
      this.setData({
        cats: (bs.categories||[]).map(c=>({name:c.name, icon:c.icon||'🏷️'})),
        uses: bs.uses||[],
        member: bs.member||{},
      }, () => this.buildLocs(bs.locations||[]));
    }).catch(()=>{});
  },

  buildLocs(locs) {
    const names = locs.map(l => app.fullLoc(l.id));
    this.setData({ locNames:names, locIds:locs.map(l=>l.id) });
  },

  setMode(e) { this.setData({ mode:e.currentTarget.dataset.m }); },

  takePhoto() {
    wx.chooseMedia({
      count:1, mediaType:['image'], sourceType:['camera','album'],
      sizeType:['compressed'],
      success: res => {
        const path = res.tempFiles[0].tempFilePath;
        this.setData({ imagePath:path, showForm:false, aiResult:null, error:'' });
        // 读取为 base64
        const fm = wx.getFileSystemManager();
        const b64 = fm.readFileSync(path, 'base64');
        this.setData({ base64:b64 }, () => this.doVision());
      },
    });
  },

  doVision() {
    const m = this.data.member;
    if (m.level !== 'vip' && m.tokens_left <= 0) {
      wx.showModal({ title:'免费额度已用完', content:'升级会员解锁无限 AI 识别', confirmText:'去升级', success:r=>{
        if (r.confirm) wx.switchTab({ url:'/pages/me/me' });
      }});
      return;
    }
    this.setData({ scanning:true });
    api.vision(this.data.base64, this.data.cats.map(c=>c.name), this.data.uses).then(res => {
      this.setData({ scanning:false });
      if (res.ok && res.result) {
        const r = res.result;
        const cat = this.data.cats.find(c=>c.name===r.cat) ? r.cat : (this.data.cats[0]?.name||'其他');
        const use = this.data.uses.includes(r.use) ? r.use : (this.data.uses[0]||'其他');
        this.setData({
          aiResult:{ model:(res.model||'').split('/').pop(), confidence:Math.round((r.confidence||0.9)*100) },
          'form.name':r.name||'未识别物品', 'form.category':cat, 'form.color':r.color||'米',
          'form.use_scene':use, showForm:true, member:res.member||this.data.member,
        });
      } else {
        this.setData({ error:res.error||'识别失败', scanning:false });
      }
    }).catch(e => this.setData({ scanning:false, error:e.error||'网络异常' }));
  },

  onField(e) { this.setData({ ['form.'+e.currentTarget.dataset.f]:e.detail.value }); },
  pickCat(e) { this.setData({ 'form.category':e.currentTarget.dataset.c }); },
  pickColor(e) { this.setData({ 'form.color':e.currentTarget.dataset.n }); },
  onUse(e) { this.setData({ 'form.use_scene':this.data.uses[e.detail.value], useIndex:Number(e.detail.value) }); },
  onLoc(e) {
    const i = Number(e.detail.value);
    this.setData({ locIndex:i, 'form.location_id':this.data.locIds[i] });
  },

  addCustom(e) {
    const kind = e.currentTarget.dataset.k;
    wx.showModal({
      title: kind==='cat'?'新增类别':'新增用途',
      content:'', editable:true, placeholderText:'输入名称',
      success: r => {
        if (!r.confirm || !r.content || !r.content.trim()) return;
        const name = r.content.trim();
        api.addTaxonomy(kind==='cat'?'cat':'use', name).then(res => {
          if (res.ok) {
            if (kind==='cat') this.setData({ cats:this.data.cats.concat([{name,icon:'🏷️'}]), 'form.category':name });
            else this.setData({ uses:this.data.uses.concat([name]), 'form.use_scene':name });
            wx.showToast({ title:'已添加' });
          } else wx.showToast({ icon:'none', title:'已存在' });
        });
      },
    });
  },

  saveItem() {
    const f = this.data.form;
    if (!f.name || !f.name.trim()) { wx.showToast({ icon:'none', title:'请填物品名称' }); return; }
    const locId = f.location_id || this.data.locIds[0] || null;
    api.addItem({
      name:f.name.trim(), category:f.category, color:f.color, use_scene:f.use_scene,
      location_id:locId, image_path:this.data.imagePath, tags:[], source:'ai',
    }).then(() => {
      wx.showToast({ title:'已入库' });
      setTimeout(()=>wx.switchTab({ url:'/pages/index/index' }), 700);
    }).catch(e => wx.showToast({ icon:'none', title:e.error||'保存失败' }));
  },

  readNfc() {
    // 小程序 NFC 能力有限，此处演示模拟读取；正式版接 wx.getNFCAdapter（安卓）
    if (wx.getNFCAdapter) {
      const adapter = wx.getNFCAdapter();
      adapter.startDiscovery({
        success: () => {
          adapter.onDiscovered(res => {
            const uid = (res.id || []).map(b => ('0'+b.toString(16)).slice(-2)).join('').toUpperCase();
            this.resolveUid(uid);
            adapter.stopDiscovery();
          });
          wx.showToast({ title:'感应中，请贴近标签' });
        },
        fail: () => this.simulateNfc(),
      });
    } else this.simulateNfc();
  },
  simulateNfc() {
    const uid = '04' + Math.random().toString(16).slice(2,10).toUpperCase();
    this.resolveUid(uid);
  },
  resolveUid(uid) {
    api.resolveNfc(uid).then(res => {
      const locName = res.found && res.binding ? app.fullLoc(res.binding.bind_id) : '未绑定（可去位置页绑定）';
      this.setData({ nfcResult:{ uid, locName } });
    }).catch(()=> this.setData({ nfcResult:{ uid, locName:'查询失败' } }));
  },
  scanCode() {
    wx.scanCode({ success: res => {
      // 二维码内容形如 .../l/{locationId} 或直接是 uid
      const uid = res.result.split('/').pop();
      this.resolveUid(uid);
    }});
  },
});
