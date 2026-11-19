# 家庭物品收纳 App + 小程序 —— Homebox 二次开发改造方案

> 产出角色：全栈智造专家团 · 全栈研发师（团长补齐源码分析部分）
> 方法论依据：`tech-stack-architecture.md`（技术选型三维打分 / 架构分层 / MVP 分级）
> 技术来源：GitHub 仓库 README 一手核实（sysadminsmedia/homebox、Duelion/homebox-companion、sweetmeats83/werehouse）
> 核实日期：2026-11-19

---

## 一、Homebox 能力盘点（可复用资产）

### 1.1 主项目概况

| 项 | 值 |
|---|---|
| 仓库 | `sysadminsmedia/homebox`（原 hay-kot/homebox 已归档，这是活跃续作） |
| 星数 / Fork | 7,918 ★ / 624 fork |
| 技术栈 | Go（后端）+ Vue/Nuxt（前端），SQLite/PostgreSQL 可选 |
| 维护状态 | 活跃，2026-11-19 仍在提交 |
| 部署 | 单二进制 / Docker，自托管 |
| 默认端口 | 7745 |
| 中文资源 | `Firfr/homebox-zh-cn`（29★，汉化版可省本地化功夫） |

### 1.2 可直接复用的数据模型与能力

| Homebox 原生能力 | 对应你的需求 | 复用方式 |
|---|---|---|
| **Item 物品模型**（名称/数量/厂商/型号/序列号/价格/备注/描述/自定义字段） | 杂物衣物记录 | 直接复用，字段够用 |
| **Location 位置树**（支持无限层级，0.27+ 区分 parent container 与 physical location） | 房间→柜子→格子 | 直接复用，无需自建 |
| **Tag 标签** | 换季/维修/纪念等分类 | 直接复用 |
| **Attachment 照片附件**（支持多图） | 物品拍照存档 | 直接复用 |
| **QR Code / Barcode + Labelmaker** | iOS NFC 受限时的二维码兜底 | 直接复用，关键资产 |
| **Search 搜索 + AI Chat 自然语言查询** | 「XX 在哪」一搜即得 | companion 已提供 24 个工具 |
| **多用户 / 权限** | 家庭共享 | 直接复用 |
| **Asset ID**（如 `032-303`） | 位置编号体系 | 直接复用 |

**结论**：物品台账、位置树、照片、标签、搜索、多用户这六块**完全不用自己写**，这是选 A 方案的根本原因——省掉约 60-70% 后端工作量。

### 1.3 AI 插件 homebox-companion（一手核实）

| 项 | 值 |
|---|---|
| 仓库 | `Duelion/homebox-companion`，421★，非官方第三方 |
| 技术栈 | Python + FastAPI（后端 8000 端口）+ Svelte（前端）+ LiteLLM |
| 核心能力 | 拍照 → AI vision 识别物品及元数据 → 人工确认 → 写入 Homebox + 自动挂照片 |
| 识别可提取字段 | 名称、数量、厂商、型号、序列号、购买价格、购买渠道、备注、描述、标签、自定义字段、Asset ID |
| 默认模型 | GPT-5.6 Luna（100 件约 $0.019，平均延迟 ~3.4s）；支持 GPT-5-nano（更快），本地 Ollama/LM Studio 实验性支持 |
| AI Chat | 24 个工具：13 个只读（list_items/search_items/get_location_tree 等，自动执行）+ 8 个写操作（需审批）+ 3 个删除（需审批） |
| 集成方式 | 浏览器 → Companion API → 再调 Homebox + AI provider；Homebox Key 只在服务端，不上浏览器 |
| 部署 | Docker 镜像 `ghcr.io/duelion/homebox-companion:latest`，一行 `docker compose up -d` |
| 连接配置 | `HBC_HOMEBOX_URL`（默认 localhost:7745）+ `HBC_HOMEBOX_API_KEY`（在 Homebox → Profile → API Keys 生成） |
| 关键环境变量 | `HBC_LLM_API_KEY`、`HBC_LLM_MODEL`、`HBC_AI_OUTPUT_LANGUAGE=Chinese`（中文输出，重要）、`HBC_PRINT_ENABLED`（标签打印）、`HBC_CORS_ORIGINS` |
| 图片质量 | 上传 Homebox 可选 raw/high/medium/low（默认 medium 1920px/75%），AI 分析始终用优化图 |
| 上传限制 | 单文件默认 20MB，单次请求 100MB，每次 capture 最多 30 张 |

**落地价值**：AI 拍照入库这块**现成可用**，只需配好 API Key 和中文输出，不用自训模型。

---

## 二、整体架构（改造后）

```
┌─────────────┐   ┌──────────────┐
│ 手机 App     │   │ 微信小程序    │  ← 家人免安装查询
│ (NFC 录入)   │   │ (扫码/搜索)   │
└──────┬──────┘   └──────┬───────┘
       │ HTTPS           │ HTTPS
       └────────┬────────┘
                ▼
       ┌────────────────┐
       │  API 网关       │  ← Nginx / Caddy，统一鉴权 + HTTPS
       │  (反向代理)      │
       └───┬────────┬────┘
           │        │
    ┌──────▼───┐  ┌─▼──────────────┐
    │ Homebox  │  │ homebox-        │
    │ :7745    │  │ companion :8000 │
    │ 物品/位置 │  │ AI识别/AI Chat  │
    │ /标签/照片│  │ (LiteLLM→GPT)   │
    └────┬─────┘  └────────────────┘
         │
   ┌─────▼──────┐
   │ PostgreSQL │ ← 家庭数据，自托管掌控
   └────────────┘
         ▲
   ┌─────┴──────┐
   │ NFC 绑定服务│ ← 新增：NFC UID ↔ Homebox Location/Item 映射
   │ (自建轻服务)│
   └────────────┘
```

**关键设计决策**：App 和小程序都不直连 Homebox/companion，而是通过 **API 网关**统一入口——解决 CORS、鉴权、HTTPS 证书三个问题，也便于后续加 NFC 绑定服务。

---

## 三、三块改造的具体接法

### 3.1 NFC 模块（核心难点：iPhone/安卓混用）

**现实约束**（必须正视，别踩坑）：
- 安卓：Web NFC（Chrome Android）可读 NDEF 标签；原生 App 用 `NDEFReader` / Android NFC API 读写完整
- iPhone：Safari **不支持** Web NFC 写入；iOS 原生 Core NFC 可**读** NDEF，但**不能写**；微信小程序 NFC 能力在 iOS 上基本不可用
- 结论：**不可能做到"iPhone 也能写 NFC 贴"**，必须双轨

**双轨方案**（推荐）：

| 端 | NFC 做法 | 体验 |
|---|---|---|
| 安卓 App | 原生 NDEF 读写，贴纸写入 Location ID | 完整：贴一下即定位箱内物品 |
| iPhone App | Core NFC 读 NDEF（只读）；写标签用**预编码 UID 贴**（淘宝买时写入固定 UID） | 读完整，写需预编码 |
| 微信小程序 | 用**二维码兜底**：Homebox 原生 QR + Labelmaker 打印贴纸，微信扫一扫直达 | 免安装，扫码体验接近碰一碰 |

**NFC 绑定服务设计**（自建轻服务，接在网关后）：

```json
// NFC 贴 ↔ Homebox 位置/物品 映射表
{
  "tag_uid": "04A1B2C3D4E5F6",        // NFC 标签唯一 ID（预编码或写入时采集）
  "bind_type": "location",            // location | item
  "bind_id": "r2b",                   // Homebox Location ID 或 Item ID
  "qr_fallback": "https://.../l/r2b", // 同一贴纸上的二维码兜底链接
  "created_at": "2026-11-19T..."
}
```

**碰一碰交互流程**（≤4 步）：
1. 手机贴近贴纸 → 读到 `tag_uid`
2. 调到绑定服务 → 查 `bind_id`
3. 调 Homebox `GET /api/v1/locations/{id}/items` 拉取该位置物品
4. App 展示"客厅·储物箱：螺丝刀套装、备用电池…"

**绑定写入流程**（首次把贴纸贴到箱子时）：
- 安卓：App 内选位置 → 写 NDEF（含 Location ID + 二维码 URL）
- iPhone：选位置 → 生成二维码 → 用 Labelmaker 打印（或用预编码 UID 贴，App 内扫码后录入 UID 到绑定服务）

**依赖借鉴**：`sweetmeats83/werehouse`（Expo + Express + SQLite，扫 NFC/QR 看箱内物品）的 NFC 交互可直接抄，省一遍踩坑。

---

### 3.2 小程序端对接

**为什么必须有小程序**：家人不会为"查一下 XX 在哪"去装 App 并注册账号——这是选双端的根本理由。小程序定位是**只读查询 + 扫码直达**（轻），录入仍以 App 为主（重）。

**对接要点**：

| 项 | 做法 |
|---|---|
| 鉴权 | 微信登录 → 后端换 Homebox API Key（专用只读用户），小程序不持有 Homebox 凭据 |
| API 层 | 所有请求走 API 网关，网关转发到 Homebox REST API，避免小程序直连自托管域名 |
| 域名 | 需已备案域名 + HTTPS（微信小程序硬性要求）；后台配置 request 合法域名 |
| 上传照片 | 小程序 `wx.uploadFile` → 网关 → Homebox attachment API |
| 扫码 | `wx.scanCode` 扫 Homebox QR → 解析 Location/Item ID → 展示详情 |
| NFC 降级 | iOS 小程序无 NFC，统一用二维码；安卓小程序可尝试 `wx.getNFCAdapter`（体验一般，不主推） |
| 框架建议 | 若团队熟 React → Taro；熟 Vue → uni-app，一套代码可同时出小程序 + H5，降低双端成本 |

**关键接口清单**（小程序侧只需这几个）：

```
GET  /api/v1/locations                    # 位置树
GET  /api/v1/locations/{id}/items         # 某位置物品列表
GET  /api/v1/items/{id}                   # 物品详情
GET  /api/v1/items/search?q=关键词         # 搜索
POST /api/gateway/wx-login                # 自建：微信登录换 token
GET  /api/gateway/nfc/{uid}               # 自建：NFC UID → 物品/位置
```

---

### 3.3 AI 拍照识别接入

**直接部署 companion，不重造轮子**：

```yaml
# docker-compose.yml（精简）
services:
  homebox:
    image: ghcr.io/sysadminsmedia/homebox:latest
    ports: ["7745:7745"]
    environment:
      - HBOX_LABEL_MAKER_PRINT_COMMAND=lp -d MyPrinter %s
    volumes: ["./homebox-data:/data"]

  companion:
    image: ghcr.io/duelion/homebox-companion:latest
    ports: ["8000:8000"]
    environment:
      - HBC_LLM_API_KEY=${OPENAI_API_KEY}
      - HBC_LLM_MODEL=gpt-5.6-luna
      - HBC_HOMEBOX_URL=http://homebox:7745
      - HBC_HOMEBOX_API_KEY=${HBC_HOMEBOX_API_KEY}
      - HBC_AI_OUTPUT_LANGUAGE=Chinese      # 关键：中文输出
      - HBC_CORS_ORIGINS=https://你的域名
      - HBC_PRINT_ENABLED=true              # 配合二维码/NFC 贴打印
    volumes: ["./companion-data:/app/data"]
```

**接入流程**：
1. Homebox → Profile → API Keys 生成 Key，填入 `HBC_HOMEBOX_API_KEY`
2. App 拍照 → 上传 Companion 识别 API → 返回结构化字段（名称/数量/厂商/位置建议/标签）
3. 用户确认/编辑 → Companion 提交到 Homebox，自动挂照片
4. 位置选择：Companion 支持扫 Homebox QR 选位置（的关键点——和 NFC 二维码体系打通）

**成本**：GPT-5.6 Luna 每 100 件约 $0.019，家庭用量一年 API 费几乎可忽略。若在意隐私，可切本地 Ollama 视觉模型（如 llava:34b，实验性支持）。

---

## 四、技术栈清单与目录结构

| 层 | 选型 | 理由 |
|---|---|---|
| 后端核心 | Homebox（Go） | 现成、活跃、数据模型贴合 |
| AI 层 | homebox-companion（Python/FastAPI + LiteLLM） | 拍照识别 + AI Chat 现成 |
| NFC 绑定服务 | Node/Express + SQLite（借鉴 werehouse） | 轻量，只做 UID↔ID 映射 |
| API 网关 | Caddy（自动 HTTPS）或 Nginx | 统一入口、证书、CORS |
| 手机 App | Flutter（一套代码 iOS+安卓） | 双端覆盖，NFC 用插件 `nfc_manager` |
| 小程序 | Taro（React）或 uni-app（Vue） | 与 App 团队技能栈一致，可复用逻辑 |
| 数据库 | PostgreSQL（Homebox 内置支持） | 家庭数据自托管掌控 |

```
home-inventory/
├── docker-compose.yml          # Homebox + companion + 网关 + NFC服务
├── gateway/                    # Caddy/Nginx 配置 + HTTPS
├── nfc-service/                # UID↔位置/物品绑定（Express+SQLite）
├── app/                        # Flutter App（iOS+安卓）
│   ├── lib/features/capture/   # 拍照识别
│   ├── lib/features/nfc/       # NFC 读写
│   └── lib/features/search/    # 搜索
├── miniprogram/                # Taro 小程序（查询为主）
└── docs/                       # 方案文档
```

---

## 五、MVP 范围（必须当期 vs 可延后）

### 必须当期（V1.0）
1. ✅ Homebox 部署 + 中文汉化 + 位置树初始化
2. ✅ companion 部署 + 拍照识别入库（含中文输出）
3. ✅ App 位置树浏览 + 手动录入 + 搜索（基本盘）
4. ✅ 安卓 NFC 完整读写 + iPhone NFC 只读 + 预编码 UID 贴
5. ✅ 小程序扫码查询（只读）
6. ✅ 二维码兜底打印（Homebox Labelmaker）

### 可延后（V1.1 / V1.2）
- ⏳ AI Chat 自然语言管理库存（companion 已有，开 `HBC_CHAT_ENABLED` 即可，可稍后开放）
- ⏳ 保质期/耗材提醒
- ⏳ 多家庭成员权限细分
- ⏳ 本地视觉模型（隐私优先时再切）

---

## 六、已知风险与规避

| 风险 | 影响 | 规避 |
|---|---|---|
| iPhone 无法写 NFC | iOS 用户体验打折 | 预编码 UID 贴 + 二维码兜底，从设计上承认这一约束 |
| companion 是非官方第三方 | Homebox 升级可能不兼容 | 锁定 Homebox 版本，companion 用固定镜像 tag 而非 latest |
| 自托管需维护服务器 | 运维负担 | 一台轻量云主机（2C4G 足够），Docker Compose 一键起；或如无运维能力改走 B 方案 |
| AI API 依赖 OpenAI | 需翻墙/付费 | 可切 LiteLLM 兼容的国内模型（DeepSeek/通义视觉）或本地 Ollama |
| 微信小程序需备案域名 | 上线前置资质 | 提前确认主体资质与域名备案状态 |
| CORS / HTTPS | 小程序与 App 连不上自托管 | 统一走 API 网关 + Caddy 自动证书 |

---

## 七、A/B 决策点（需你拍板）

1. **自托管 vs 免运维**：A 方案要维护一台服务器（2C4G 轻量云约 ¥300-600/年）。若你不想运维 → 转 B/C 方案。
2. **AI 用云 API vs 本地模型**：云 API（GPT-5.6 Luna）便宜省心但依赖外网；本地 Ollama 视觉模型隐私好但需好显卡。
3. **App 开发方式**：Flutter 双端（推荐）vs 先只做安卓原生验证 NFC。

---

**本次产出完毕。可继续深化方向**：
1. 细化 NFC 绑定服务的完整 API 设计（UID 采集、绑定流程、冲突处理）+ Flutter `nfc_manager` 具体代码骨架
2. 出一份 Homebox + companion 的 `docker-compose.yml` 完整可部署文件 + 首启初始化清单

[技术研发方案]
