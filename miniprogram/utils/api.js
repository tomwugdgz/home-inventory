/**
 * 家物志小程序 · API 封装
 * 统一请求后端 8892，错误集中处理
 */
const { API_BASE } = require('../config.js');

function request(path, method, data) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: API_BASE + path,
      method: method || 'GET',
      data: data || {},
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res.data || { error: '服务器错误 ' + res.statusCode });
        }
      },
      fail(err) {
        reject({ error: '连接失败，请检查：① 电脑服务器是否运行 ② 手机是否同WiFi ③ config.js 的IP是否正确' });
      },
    });
  });
}

module.exports = {
  base: API_BASE,
  health: () => request('/api/health'),
  bootstrap: () => request('/api/bootstrap'),

  listLocations: () => request('/api/locations'),
  addLocation: (name, parent_id) => request('/api/locations', 'POST', { name, parent_id }),
  updateLocation: (id, name, parent_id) => request('/api/locations/' + id, 'PUT', { name, parent_id }),
  deleteLocation: (id) => request('/api/locations/' + id, 'DELETE'),

  listItems: () => request('/api/items'),
  addItem: (data) => request('/api/items', 'POST', data),
  updateItem: (id, data) => request('/api/items/' + id, 'PUT', data),
  deleteItem: (id) => request('/api/items/' + id, 'DELETE'),

  listCategories: () => request('/api/categories'),
  listUses: () => request('/api/uses'),
  addTaxonomy: (kind, name) => request('/api/taxonomy', 'POST', { kind, name }),
  deleteTaxonomy: (kind, name) => request('/api/taxonomy/' + kind + '/' + encodeURIComponent(name), 'DELETE'),

  getMember: () => request('/api/member'),
  upgrade: () => request('/api/member/upgrade', 'POST'),
  downgrade: () => request('/api/member/downgrade', 'POST'),
  ledger: () => request('/api/ledger'),

  // 拍照识别：传图片 base64（小程序用 wx.getFileSystemManager().readFile 得到）
  vision: (base64Image, cats, uses) => request('/api/vision', 'POST', {
    image_url: 'data:image/jpeg;base64,' + base64Image,
    cats: cats || [], uses: uses || [],
  }),

  // NFC/二维码绑定
  bindNfc: (uid, bindType, bindId) => request('/api/nfc/bind', 'POST', { uid, bind_type: bindType, bind_id: bindId }),
  resolveNfc: (uid) => request('/api/nfc/resolve?uid=' + encodeURIComponent(uid)),
};
