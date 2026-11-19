# 家物志 · 家庭物品收纳管理

> 2026-11-19 · Phase 1 本地服务器版
> **H5 Demo + REST API + SQLite + 微信小程序（五页）**
> GitHub：https://github.com/tomwugdgz/home-inventory

---

## 一、能做什么

拍照 → AI 自动识别物品名 / 类别 / 颜色 / 用途 → 记下放在哪 → 以后一搜就找到。

- **拍照识别**：真实调用本地 AI，会员功能，消耗 Token（免费 10 次）
- **NFC 贴**：贴纸只存 UID，数据云端绑定；iPhone 无法写 NFC，走「预编码贴 + 云端绑定」，并用二维码兜底
- **位置树**：房间 → 柜子 → 格子，无限层级，可自定义
- **自定义**：类别、用途、物品字段全部可增删改
- **商业模式**：AI 会员订阅 + NFC 贴实体耗材复购

## 二、架构

| 层 | 文件 | 端口 | 说明 |
|---|---|---|---|
| H5 Demo | `index.html` + `server.py` | 8891 | 浏览器版，localStorage 持久化 |
| REST API | `backend/api_server.py` | **8892** | SQLite 数据库，局域网多设备共享 |
| 微信小程序 | `miniprogram/` | — | 五个页面，通过 API 读写同一数据库 |

- 数据库：`backend/data/jiawuzhi.db`（SQLite，Python 标准库零依赖）
- `backend/database.py` 启动时自动建表 + 灌默认数据：8 个位置 / 7 个类别 / 8 个用途 / 6 件物品，幂等可重复运行
- AI Key 只在服务端从 `.env` 读取，**不暴露给浏览器或小程序**

## 三、启动（你的电脑当服务器）

```bash
cd d:/Mirofish/home-inventory-demo
copy config.example.env .env      # 填入你的 AI_KEY
python server.py                  # H5 Demo  → http://localhost:8891
python backend/api_server.py      # REST API → http://localhost:8892/api/health
```

两个命令各开一个终端。手机连**同一个 WiFi**后访问：

- H5 Demo：`http://192.168.3.167:8891`
- 后端 API：`http://192.168.3.167:8892/api/bootstrap`

> 手机打不开？检查：① 同 WiFi（不是访客网 / 不是流量）② Windows 防火墙放行 8891、8892 端口（首次弹窗勾「专用网络」）③ IP 变了用 `ipconfig` 查，并同步改 `miniprogram/config.js` 的 `API_BASE`。

## 四、微信小程序导入（真机预览）

1. 打开**微信开发者工具** → 导入项目 → 目录选 `miniprogram/`，AppID 选「测试号」
2. 详情 → 本地设置 → 勾选 **「不校验合法域名、web-view、TLS 版本以及 HTTPS 证书」**（开发阶段访问局域网 http 必需）
3. 确认 `miniprogram/config.js` 的 `API_BASE` 是你电脑的局域网 IP
4. 点「编译」→ 五个 tab：首页 / 找东西 / 记录 / 位置 / 更多
5. 点「预览」扫码真机测试，手机必须与电脑同 WiFi

> 已知平台限制：iOS 小程序不能写 NFC；安卓可用 `wx.getNFCAdapter()` 读 UID，写 NDEF 需真机适配。二维码流程两端通用。

## 五、REST API 一览

```
GET    /api/health                 健康检查
GET    /api/bootstrap              一次性拉全量数据（小程序冷启动）
GET/POST   /api/locations          位置树
GET/POST   /api/items              物品
PUT/DELETE /api/items/{id}         改 / 删物品
GET/POST   /api/taxonomy           分类与用途
GET    /api/member                 会员与 Token
POST   /api/member/token/consume   消耗 Token
POST   /api/member/upgrade         升级 / 降级会员
POST   /api/vision                 AI 拍照识别代理
GET    /api/nfc/resolve?uid=...    UID 解析
POST   /api/nfc/bind               NFC 绑定
```

## 六、方案文档（docs/）

| 文件 | 内容 |
|---|---|
| `00-项目档案.md` | 项目六要素 / 架构决策 / 里程碑 / 技术债 / 复盘卡 |
| `01-homebox-改造方案.md` | Homebox 能力盘点 / NFC + 小程序 + AI 三块接法 / MVP 分级 |
| `02-方案对比表.md` | A/B/C 十维打分（A 方案 3.49 胜出） |
| `03-商业模式与会员体系.md` | NFC 贴耗材 + AI 会员双引擎 / SKU / Token 成本测算 |
| `04-NFC写入与Token计量技术方案.md` | UID 云端绑定 / 写入流程 / API / Token 计量 / 5 张表设计 |

## 七、安全说明

- `.env`（含真实 AI Key）已加入 `.gitignore`，**不上传**
- 仓库只有 `config.example.env` 模板，不含真实 Key
- `backend/data/*.db` 不上传（含本机真实数据）
- 已核验公开文件中无 Key / 无 PAT 痕迹

## 八、下一步

1. 真机 NFC 联调（安卓 NDEF 写入 + iPhone 预编码贴）
2. 微信小程序提交审核需：主体认证 + 域名备案 + HTTPS + 支付商户号
3. 商业模式待拍板：贴纸主题、家庭装 6 色、年付主推、¥3/30 次加购包
