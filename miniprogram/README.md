# 家物志 · 微信小程序（前端）

> 配套后端：`../backend/api_server.py`（端口 8892）+ SQLite 数据库

## 一、跑起来（3 步）

### 第 1 步：启动后端
```bash
cd d:/Mirofish/home-inventory-demo/backend
python api_server.py
```
看到「局域网/小程序: http://你的IP:8892/api/bootstrap」即成功。

### 第 2 步：确认 IP 一致
打开 `miniprogram/config.js`，确认 `API_BASE` 是你电脑的局域网 IP（默认 `192.168.3.167`）。
电脑 IP 会变，变了就改这里一处。

### 第 3 步：导入微信开发者工具
1. 打开微信开发者工具 → 导入项目
2. 目录选 `d:/Mirofish/home-inventory-demo/miniprogram`
3. AppID 选「测试号」（个人没小程序账号也能用）
4. **关键**：详情 → 本地设置 → 勾选「不校验合法域名、web-view、TLS 版本以及 HTTPS 证书」
   （不勾的话小程序会拦截 http 局域网请求）
5. 编译运行，用手机扫码「预览」即可真机测试

## 二、功能

| 页面 | 功能 |
|---|---|
| 首页 | 统计 / 会员条 / 拍照+NFC 快捷入口 / 最近物品 |
| 找东西 | 搜名称·类别·位置·颜色 / 物品详情 / 改位置 / 删除 |
| 记录 | 拍照 AI 识别（物品名/颜色/用途/类别）/ NFC 感应 / 二维码兜底 / 自定义分类 |
| 位置 | 无限层级位置树 / 新建·改名·删除 / 查看位置物品 |
| 更多 | 会员升级 / Token 流水 / 类别用途管理 / NFC 商城 |

所有数据通过 API 存后端 SQLite，**局域网多设备共享同一份数据**。

## 三、目录结构

```
miniprogram/
├── app.js / app.json / app.wxss   全局
├── config.js                      后端 IP 配置（唯一需改处）
├── project.config.json            开发者工具配置
├── sitemap.json
├── assets/                        tabBar 图标（10 个）
├── utils/api.js                   API 封装
└── pages/
    ├── index/    首页
    ├── find/     找东西
    ├── capture/  记录（拍照+NFC）
    ├── location/ 位置
    └── me/       更多
```

## 四、说明与限制

- **测试号即可跑**：无需注册小程序、无需域名备案（开发环境关闭域名校验即可）
- **NFC**：小程序 iOS 无 NFC 权限，走二维码兜底；安卓可接 `wx.getNFCAdapter`（当前为演示流程）
- **支付**：会员/NFC 商城为演示，正式版需企业主体 + 微信支付商户号
- **上线**：正式发布需注册小程序（企业/个体户主体）+ 备案域名 + HTTPS（按商业模式文档 C1 决策走 SaaS 云）

## 五、关于 input Editable 弹窗

新增类别/用途用了 `wx.showModal` 的 `editable: true`（基础库 2.17.1+），老版本会退化为普通弹窗。
