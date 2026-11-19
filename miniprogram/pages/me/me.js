const app = getApp();
const api = require('../../utils/api.js');

Page({
  data: { member:{}, cats:[], uses:[], ledger:[], taxDialog:null, taxList:[], taxKind:'cat', taxNew:'' },

  onShow() { this.load(); },
  load() {
    Promise.all([app.refreshBootstrap(), api.ledger()]).then(([bs, led]) => {
      this.setData({
        member: bs.member||{}, cats:bs.categories||[], uses:bs.uses||[],
        ledger:(led.ledger||[]).map(l=>({...l, timeStr:this._ago(l.created_at)})),
      });
    }).catch(()=>{});
  },
  _ago(t) {
    const h = Math.floor((Date.now()-t)/3600000);
    return h<1?'刚刚':(h<24?h+'小时前':Math.floor(h/24)+'天前');
  },

  upgrade() {
    wx.showModal({ title:'升级会员', content:'演示版：确认升级为会员（¥12/月）？正式版接微信支付。', success:r=>{
      if(!r.confirm) return;
      api.upgrade().then(()=>{ wx.showToast({title:'已升级'}); this.load(); });
    }});
  },
  downgrade() {
    api.downgrade().then(()=>{ wx.showToast({title:'已切回免费版'}); this.load(); });
  },

  manageTax(e) {
    const kind = e.currentTarget.dataset.k;
    const list = kind==='cat' ? this.data.cats : this.data.uses;
    this.setData({ taxDialog:{ title:kind==='cat'?'管理类别':'管理用途' }, taxKind:kind, taxList:list, taxNew:'' });
  },
  closeTax(){ this.setData({ taxDialog:null }); },
  noop(){},
  onTaxNew(e){ this.setData({ taxNew:e.detail.value }); },
  addTax(){
    const name=this.data.taxNew.trim();
    if(!name){ wx.showToast({icon:'none',title:'请输入名称'}); return; }
    api.addTaxonomy(this.data.taxKind, name).then(res=>{
      if(!res.ok){ wx.showToast({icon:'none',title:'已存在'}); return; }
      wx.showToast({title:'已添加'});
      const list = this.data.taxKind==='cat'
        ? this.data.cats.concat([{name,icon:'🏷️'}])
        : this.data.uses.concat([name]);
      this.setData({ taxList:list, taxNew:'' }); this.load();
    });
  },
  removeTax(e){
    const name=e.currentTarget.dataset.n;
    wx.showModal({ title:'删除标签', content:'删除「'+name+'」？已有物品的标签不受影响。', success:r=>{
      if(!r.confirm) return;
      api.deleteTaxonomy(this.data.taxKind, name).then(()=>{
        this.setData({ taxList:this.data.taxList.filter(x=>x.name!==name) });
        wx.showToast({title:'已删除'}); this.load();
      });
    }});
  },

  buyTags(){
    wx.showModal({ title:'购买 NFC 贴', content:'家庭装 30 枚 ¥49（演示：模拟下单）', success:r=>{
      if(!r.confirm) return;
      wx.showToast({title:'下单成功 · 30枚到账'});
    }});
  },
});
