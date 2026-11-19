const app = getApp();
const api = require('../../utils/api.js');

Page({
  data: {
    tree: [], roots: [], allLocs: [], items: [],
    dialog: null, parentNames: [], parentIds: [], parentIndex: 0,
    locSheet: null,
  },

  onShow() { this.load(); },

  load() {
    app.refreshBootstrap().then(bs => {
      const locs = bs.locations || [];
      const items = bs.items || [];
      this.setData({ allLocs: locs, items, roots: locs.filter(l => !l.parent_id) }, () => this.buildTree());
    }).catch(e => wx.showToast({ icon:'none', title:'加载失败' }));
  },

  buildTree() {
    const { allLocs, items } = this.data;
    const countOf = lid => items.filter(i => i.location_id === lid).length;
    const childrenOf = pid => {
      const kids = allLocs.filter(l => l.parent_id === pid);
      return kids.map(k => ({
        id:k.id, name:k.name, depth:0, count:countOf(k.id), open:false,
      }));
    };
    const tree = this.data.roots.map(r => {
      // 递归收集后代
      const descendants = [];
      const walk = (pid, depth) => {
        allLocs.filter(l => l.parent_id === pid).forEach(k => {
          descendants.push({ id:k.id, name:k.name, depth, count:countOf(k.id) });
          walk(k.id, depth+1);
        });
      };
      walk(r.id, 0);
      let total = countOf(r.id);
      descendants.forEach(d => total += d.count);
      return { id:r.id, name:r.name, open:false, totalCount:total,
               childCount:descendants.length, children:descendants };
    });
    this.setData({ tree });
  },

  toggle(e) {
    const id = e.currentTarget.dataset.id;
    const tree = this.data.tree.map(t => t.id===id ? {...t, open:!t.open} : t);
    this.setData({ tree });
  },

  // ---- 新建 ----
  addRoot() {
    this.setData({
      dialog: { title:'新建房间', needName:true, needParent:false,
                placeholder:'如：阳台储物柜', name:'', isEdit:false },
    });
  },
  addChild(e) {
    const pid = e.currentTarget.dataset.id;
    const parent = this.data.allLocs.find(l => l.id===pid);
    this.setData({
      dialog: { title:'新建子位置', needName:true, needParent:false,
                placeholder:'如：第二层 / 靠门左边', name:'', isEdit:false, parentId:pid },
    });
  },

  // ---- 编辑 ----
  editLoc(e) {
    const id = e.currentTarget.dataset.id;
    const l = this.data.allLocs.find(x => x.id===id);
    if (!l) return;
    const parents = this.data.allLocs.filter(x => x.id!==id && !this._isDescendant(x.id, id));
    const parentIds = [''].concat(parents.map(p=>p.id));
    const parentNames = ['（顶级房间）'].concat(parents.map(p=>p.name));
    const parentIndex = l.parent_id ? Math.max(0, parentIds.indexOf(l.parent_id)) : 0;
    this.setData({
      dialog: { title:'编辑位置', needName:true, needParent:true, placeholder:'位置名称',
                name:l.name, isEdit:true, editId:id },
      parentIds, parentNames, parentIndex,
    });
  },
  _isDescendant(candidate, ancestor) {
    let cur = this.data.allLocs.find(x=>x.id===candidate);
    while (cur && cur.parent_id) {
      if (cur.parent_id === ancestor) return true;
      cur = this.data.allLocs.find(x=>x.id===cur.parent_id);
    }
    return false;
  },

  onName(e) { this.setData({ 'dialog.name': e.detail.value }); },
  onParent(e) { this.setData({ parentIndex: Number(e.detail.value) }); },
  noop() {},
  closeDialog() { this.setData({ dialog:null }); },

  confirmDialog() {
    const d = this.data.dialog;
    const name = (d.name||'').trim();
    if (!name) { wx.showToast({ icon:'none', title:'请输入名称' }); return; }
    if (d.isEdit) {
      const pid = this.data.parentIds[this.data.parentIndex] || null;
      api.updateLocation(d.editId, { name, parent_id: pid }).then(() => {
        this.setData({ dialog:null }); wx.showToast({ title:'已保存' }); this.load();
      }).catch(err => wx.showToast({ icon:'none', title:err.error||'失败（可能形成循环层级）' }));
    } else {
      api.addLocation(name, d.parentId || null).then(() => {
        this.setData({ dialog:null }); wx.showToast({ title:'已添加' }); this.load();
      }).catch(err => wx.showToast({ icon:'none', title:err.error||'失败' }));
    }
  },

  deleteLoc() {
    const d = this.data.dialog;
    wx.showModal({ title:'删除位置', content:'删除后该位置的物品移到「未分类」，不会丢失。确定？', success:r => {
      if (!r.confirm) return;
      api.deleteLocation(d.editId).then(() => {
        this.setData({ dialog:null }); wx.showToast({ title:'已删除' }); this.load();
      });
    }});
  },

  showItems(e) {
    const id = e.currentTarget.dataset.id;
    const l = this.data.allLocs.find(x=>x.id===id);
    const its = this.data.items.filter(i => i.location_id===id);
    this.setData({ locSheet: { name:l?l.name:'位置', items:its } });
  },
  closeLocSheet() { this.setData({ locSheet:null }); },
});
