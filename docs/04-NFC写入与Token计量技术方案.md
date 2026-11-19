# NFC 写入与 Token 计量技术方案

> 产出角色：全栈智造专家团 · 全栈研发师
> 方法论依据：`tech-stack-architecture.md`（技术选型三维打分 / 架构分层 / MVP 分级 / 非功能性基线 / 多端适配）
> 口径基线：与 `01-homebox-改造方案.md`（Homebox 二次开发路线）保持一致，本文为其在 NFC 商业化与 AI 会员化两个方向上的增量设计
> 上游输入：Tom 2026-11-19 本轮亲述需求（NFC 贴面向用户写入并作为耗材商品售卖；AI 拍照提取颜色/用途/物品名等字段，会员专用并需 Token 计量与付费墙）
> 核实事实来源：`sysadminsmedia/homebox`（Go+Vue, 7745）、`Duelion/homebox-companion`（Python FastAPI 8000 + Svelte + LiteLLM）、平台 NFC 硬约束
> 口径声明（2026-11-19 二次修订）：本方案已与 `03-商业模式与会员体系.md` 对齐——会员档位（免费 10 / 个人 300 / 家庭 1000 共享）、AI 抽取五字段（物品名/颜色/用途/类别/材质）、超额降级为手动录入、支付渠道与权益解耦均以其为准。差异项已在正文标注。
> ✅ 数据模型共识（见 3.8）：初期曾讨论"给物品/位置表加 `nfc_uid` 字段"，经与选品洞察师对齐后达成一致——采用独立 `nfc_binding` 映射表，需求侧已撤回加字段建议，03 文档 3.2 节已同步澄清。理由：不改 Homebox 第三方源码 + 支持换绑/审计/一物多贴，功能等价。**D6 已收口，无需团长裁决**。

## 〇、本轮目标与口径变化（先对齐再动手）

### 0.1 新增需求拆解

| # | Tom 原话 | 技术翻译 | 商业含义 |
|---|---|---|---|
| 1 | NFC 贴支持给用户写入，通过售卖 NFC 贴增加用户粘性 | 贴纸从"出厂即固定绑定"变为"用户购买后自行激活绑定"；用户感知是"我把信息写进了贴纸"，技术实现是"云端绑定 UID" | 实体贴纸 = 可复购耗材，是收入主品；App 是免费入口 |
| 2 | AI 拍照后记录颜色、用途、物品名等字段来提效 | 在 companion 现有字段基础上扩展 **color / usage_scene / category / material**（物品名为原有字段，共五字段，对齐 03 文档第六章） | AI 识别从"人人可用"变为"会员权益"，需要计量与付费墙 |

> 对齐说明：03 文档 4.2 表格要求「个人/家庭会员全字段、免费用户仅基础（物品名）」。因此**四个扩展字段的写入是会员专属**，前端对免费用户隐藏/锁定这四个字段的自动填充（但允许手动填写），这是付费墙在数据层的落点（见 4.5）。

### 0.2 与 01 方案的关键口径变化（必须显式声明）

01 方案定位是**家庭自托管工具**（单家庭、单机、无付费）。本轮加入"卖贴纸 + 卖会员"后，系统性质变为**面向多用户的小型 SaaS**。以下三处口径必须调整，否则会在开发中爆雷：

| 项 | 01 方案口径 | 本轮调整 | 调整理由 |
|---|---|---|---|
| 数据库 | NFC 服务用 SQLite | **共用 Homebox 的 PostgreSQL，独立 schema `nfc_saas`** | 参考文件明确"SQLite 禁止用于多用户 Web 生产"；付费/流水/幂等需要事务与唯一约束；避免两套数据源对账 |
| 用户体系 | Homebox 多用户即全部用户 | **自建 `app_user`（消费者）+ 家庭组，Homebox 用户作为内部服务账号** | 买家 ≠ 家庭管理员；Homebox 不该暴露给付费用户直连 |
| 部署形态 | 纯自托管 | **云端 SaaS 主形态，保留自托管兼容模式** | 耗材发货与会员支付需要公网可达；自托管用户可自带 AI Key 免会员（见 6.6） |
| 计费体系 | 无（家庭内部免费用） | **三级会员 + 加购包 + 支付渠道解耦（对齐 03 文档）** | Tom 本轮明确 AI 会员化；V1.0 先加购包验证、V1.1 上订阅（见 11） |
| AI 抽取字段 | 原有 12 类字段 | **新增类别字段，共五字段；免费仅物品名** | 03 文档第六章把颜色/用途/类别/材质定义为会员核心价值点（见 4.2） |

> **矛盾上报（团长裁决点 C1）**：本方案把项目从"自托管工具"推向"SaaS 商品"，这与 01 方案中"Tom 不想运维"的 A/B 决策点直接相关。若团长/产品侧确认仍以纯自托管为主，则会员付费墙需改为"自带 Key 免费用 + 贴纸在淘宝等第三方渠道售卖"，本文第六、十一章需整体重做。**本文按"SaaS 主形态"撰写**，请团长确认。

### 0.3 三个不可动摇的设计原则

1. **贴纸不存业务数据，只存 UID**（第一章详述）——这是"同一批贴纸跨 iPhone / 安卓 / 小程序通用"的唯一技术前提，也是能卖的前提。
2. **付费边界放在自建网关，不放进 companion**——companion 是第三方组件，不认识会员/Token，只做被保护的 AI 执行单元。
3. **不引入微服务、分布式事务、消息队列**——日活千级以内，模块化单体 + PostgreSQL 事务足够（参考文件第六章"反对过度设计"）。

---

## 一、核心架构决策：NFC 贴"物理锚点 + 云端绑定"

### 1.1 定义

- **物理锚点**：贴纸内只有一个全球唯一、出厂锁定、只读的 UID（NTAG213/215 的 7-byte NUID）。它的作用是"把现实世界的一个箱子/一件物品，映射成云端的一个不可伪造的 ID"。
- **云端绑定**：业务数据（属于谁、对应哪个 Homebox Location/Item、贴了几张照片）全部存在云端 `nfc_binding` 表。碰一碰时手机读 UID → 查云端 → 返回数据。

一句话：**贴纸是"钥匙"，不是"保险箱"。保险箱（业务数据）在云上，钥匙丢了换一把重新配就行。**

### 1.2 为什么坚决不往贴纸里塞完整业务数据（四个硬论据）

| 论据 | 具体数据/事实 | 后果 |
|---|---|---|
| **容量不够** | NTAG213 NDEF 可用约 137 字节，NTAG215 约 492 字节；而一条 Homebox Item 含名称/数量/厂商/型号/序列号/价格/备注/自定义字段，JSON 轻松超 500 字节 | 塞不下；且 UID 类标签的 UTF-8 中文每字 3 字节，中文场景更紧张 |
| **iPhone 写不了** | iOS Safari 无 Web NFC；Core NFC 只能**读** NDEF，**不能写**。安卓原生能写，但用户用 iPhone 买了贴纸就写不进去 | 若业务依赖"写贴纸"，等于放弃 iPhone 用户（约一半市场），贴纸卖不动 |
| **改数据要重写** | 用户重命名箱子、物品换位置、改颜色 → 若数据在贴纸里，必须掏出手机重新贴一遍写入 | 体验灾难，且 iPhone 用户永远无法更新 |
| **多端无法通用** | 安卓写入的 NDEF 格式，iPhone 读出后解释逻辑、小程序 `wx.getNFCAdapter` 支持度都不一致 | 同一批贴纸在不同端表现不同 → 售后成本爆炸，商品口碑崩 |

**反证**：如果走"贴纸存完整数据"路线，会出现"安卓用户写的贴 iPhone 读不出中文""用户改名必须重写贴纸""iPhone 用户买回去是废纸"三类必然投诉。这条路直接堵死。

### 1.3 芯片选型对比（决策表）

| 维度 | NTAG213 | NTAG215 | NTAG216 | 选型 |
|---|---|---|---|---|
| NDEF 可用容量 | ~137 B | ~492 B | ~828 B | **NTAG213**（只存 UID + 可选短 URL，够用且最便宜） |
| 单价（千片级） | 最低 | 中 | 高 | NTAG213 |
| UID 唯一性 | 7-byte NUID，出厂锁定 | 同 | 同 | 三者一致 |
| 安卓 NDEF 写 URL 增强 | 放不下完整 URL | 可放短链 | 可放长链 | 增强需求选 NTAG215 |
| 供应链成熟度 | 极高 | 极高 | 中 | 均可 |

**结论（A/B 决策点 D1）**：
- **D1-A 推荐**：主推 **NTAG213 预编码 UID 贴**（成本最低，UID-only 方案下容量完全够），BOM 成本可控在个位数分/片，适合做引流耗材。
- **D1-B 备选**：若要做"安卓碰一碰直接打开小程序短链"的增强款，用 **NTAG215**，写入一条 `https://短链/{uid}`（约 30-40 B）。**但该 URL 仅作快捷方式，业务判定仍以 UID 查云端为准**——即使 URL 被篡改也不影响数据安全。

### 1.4 "用户写入"的用户感知 vs 技术实现（关键话术与交互设计）

Tom 说的"支持给用户写入"，**不能实现为字面意义的"写 NFC 芯片"**（iPhone 做不到），而应实现为：

> 用户在 App 里选好位置/物品 → 点"写入贴纸" → 碰一下贴纸 → App 读到 UID → 云端绑定 → 提示"写入成功"。

用户的心智模型是"我把信息写进贴纸了"，实际发生的是"云端把 UID 和我的物品绑了"。**这个体验一身两得**：跨端通用 + 无写芯片失败率。文案上如实说"绑定成功，贴纸已关联到客厅储物箱"，避免"写入芯片"的技术误导（也规避 iOS 审核中"功能与描述不符"风险）。

### 1.5 为什么这是"能卖"的技术前提

1. **库存可预测**：出厂预编码 UID 列表可在发货前批量导入 `nfc_sticker` 表，贴纸与订单可一一对应。
2. **跨端不挑设备**：iPhone / 安卓 / 小程序都能用 → 用户不会因换手机而作废 → 复购意愿成立。
3. **可防伪防串货**：UID + 激活码双因子（第三章 3.5），比二维码更难批量复制（NFC 芯片克隆门槛高于截图二维码）。
4. **可复购钩子**：贴纸用完/想给新箱子贴 → 再买；App 内"我的贴纸 12/20 已用"自然引导复购。

---

## 二、写入 / 绑定完整流程（每端 ≤4 步）

### 2.1 全生命周期链路

```
出厂预编码 UID（芯片锁定 7-byte NUID）
   ↓ 供应商交付 UID 清单 + 印刷激活码（刮刮层）
批量导入 nfc_sticker 表（status=manufactured）
   ↓ 电商售卖
用户购买收货（贴纸 status=shipped）
   ↓ App 扫码/碰一碰读 UID + 输入激活码
激活（status=activated，归属到 app_user）
   ↓ 用户在 App 选 Homebox 位置/物品
绑定（status=bound，写 nfc_binding）
   ↓ 日常碰一碰
读 UID → 查绑定 → 展示物品列表（Homebox API）
```

### 2.2 三端路径对比（逐端核对，不搞"一套代码全端通用"）

| 端 | 读 UID 方式 | 绑定方式 | 业务判定依据 | 限制与规避 |
|---|---|---|---|---|
| **安卓 App** | `nfc_manager` / Android NFC API 原生读 UID + NDEF | 云端绑定；**可选增强**：写一条短链 NDEF 到 NTAG215 | UID 查云端（NDEF URL 仅快捷方式） | 需 `android.permission.NFC`；Activity 需 `enableForegroundDispatch` 避免系统弹窗打断 |
| **iPhone App** | Core NFC `NFCTagReaderSession` 读 UID（只读） | **只能云端绑定**，无法写芯片 | UID 查云端 | 必须申请 NFC 权限描述（`NFCReaderUsageDescription`）；隐私清单 PrivacyInfo 需声明；iPhone 8+ / iOS 13+ |
| **微信小程序** | `wx.getNFCAdapter`（仅安卓、体验一般）→ **主推二维码** | 扫 Homebox QR / 自建短链二维码 → 云端绑定 | 二维码中的 UID 参数查云端 | iOS 小程序无 NFC；统一二维码兜底，与 Homebox Labelmaker 打印体系打通 |
| **鸿蒙 App（V1.1）** | ArkTS `@ohos.nfc.tag` 读 UID | 云端绑定 | UID 查云端 | ArkTS 禁 any、UIAbility 生命周期与 Android 不同，需独立适配层；V1.0 不做，见第六章 |

### 2.3 交互步骤（严格 ≤4 步）

**A. 首次激活 + 绑定（用户拿到新贴纸，全程 4 步）**

1. 打开 App → "我的贴纸" → 点「激活新贴纸」
2. 碰一下贴纸（或扫包装二维码）→ App 自动读到 UID
3. 刮开激活码输入 → 选要贴的位置/物品（如"客厅·储物箱"）
4. 点「完成」→ 提示"已绑定到客厅储物箱"→ 贴上即可

**B. 日常碰一碰查询（4 步）**

1. 手机贴近贴纸 → App/小程序自动读 UID
2. 网关调 `GET /api/v1/nfc/resolve?uid=xxx` → 拿 `bind_type` + `bind_id`
3. 调 Homebox `GET /api/v1/locations/{id}/items` 拉物品列表
4. 展示"客厅·储物箱：螺丝刀套装、备用电池…"（小程序为只读页）

### 2.4 防冲突 / 防冒领在流程中的位置

- 激活码在第 3 步校验 → 证明"你买了这张贴"，捡到贴纸的人没有激活码无法绑定。
- 同一 UID 并发激活 → 数据库唯一索引 + 事务，失败方返回 `409 UID_ALREADY_ACTIVATED`。
- 已绑定贴纸被他人碰一碰 → 只能**读**，不能改绑定；解绑需 owner 身份 + 二次确认。

---

## 三、API 设计（NFC 绑定服务）

### 3.1 接口清单

| 方法 | 路径 | 鉴权 | 幂等 | 说明 |
|---|---|---|---|---|
| POST | `/api/v1/nfc/stickers/activate` | 用户 JWT | 是（`request_id`） | UID 注册激活（UID + 激活码） |
| POST | `/api/v1/nfc/bindings` | 用户 JWT + owner 校验 | 是 | 绑定到 Homebox 位置/物品 |
| DELETE | `/api/v1/nfc/bindings/{uid}` | 用户 JWT + owner 校验 | 是 | 解绑 |
| GET | `/api/v1/nfc/resolve?uid={uid}` | 用户 JWT | 否（读） | 按 UID 查物品/位置 |
| GET | `/api/v1/nfc/stickers` | 用户 JWT | 否 | 我的贴纸列表（分页） |
| GET | `/api/v1/nfc/bindings/{uid}/audit` | 用户 JWT | 否 | 绑定变更审计（申诉用） |

### 3.2 UID 注册（激活）

**请求**
```http
POST /api/v1/nfc/stickers/activate
Authorization: Bearer <jwt>
Content-Type: application/json
{ "uid": "04A1B2C3D4E5F6", "activation_code": "K7M9-2XP4-8QTR", "request_id": "9f1c...uuid" }
```

**响应 200**
```json
{ "code": 0, "message": "ok", "data": { "uid": "04A1B2C3D4E5F6", "status": "activated", "owner_user_id": "u_10086", "activated_at": "2026-11-19T10:22:31Z" } }
```

**错误码**：`400 ACTIVATION_CODE_INVALID`（激活码错/已用）、`409 UID_ALREADY_ACTIVATED`（被激活）、`404 UID_NOT_IN_INVENTORY`（非本系统出货贴纸，防伪造）。

### 3.3 绑定 / 解绑

**请求**
```http
POST /api/v1/nfc/bindings
{ "uid": "04A1B2C3D4E5F6", "bind_type": "location", "bind_id": "r2b", "request_id": "c33a...uuid" }
```
`bind_type` 枚举：`location` | `item`。

**响应 200**
```json
{ "code": 0, "data": { "binding_id": 8821, "uid": "04A1B2C3D4E5F6", "bind_type": "location", "bind_id": "r2b", "status": "active", "bound_at": "2026-11-19T10:25:02Z" } }
```

**解绑**：`DELETE /api/v1/nfc/bindings/04A1B2C3D4E5F6` → `{ "code": 0, "data": { "status": "unbound" } }`。解绑后置 `nfc_binding.status=unbound`、贴纸回 `activated`，保留历史行不物理删除（审计）。

### 3.4 按 UID 查物品（碰一碰主链路）

**请求**：`GET /api/v1/nfc/resolve?uid=04A1B2C3D4E5F6`

**响应 200**
```json
{
  "code": 0,
  "data": {
    "uid": "04A1B2C3D4E5F6",
    "bind_type": "location",
    "bind_id": "r2b",
    "homebox": { "location_name": "客厅·储物箱", "item_count": 12 },
    "items_preview": [
      { "id": "i_231", "name": "螺丝刀套装", "quantity": 1 },
      { "id": "i_235", "name": "备用电池", "quantity": 8 }
    ],
    "qr_fallback": "https://短链/l/r2b"
  }
}
```

> 归属校验：`resolve` 只返回**当前用户所属家庭组**可见的绑定；他人 UID 返回 `404 BINDING_NOT_FOUND`（不泄露贴纸存在性，防枚举）。

### 3.5 防冲突 / 防冒领 / 归属校验（三条铁律）

1. **唯一约束**：`UNIQUE(uid, status)` where `status='active'`，一个贴纸同时只能有一条有效绑定。
2. **激活码二次因子**：`activation_code_hash`（bcrypt）存表，激活时校验并置 `used_at`；激活码与 UID 在发货清单中一一配对，扫码出库时绑定。
3. **归属校验**：绑定前调用 Homebox `GET /api/v1/locations/{id}` 校验该 ID 属于用户家庭组；越权返回 `403 RESOURCE_NOT_OWNED`。写操作全部走 owner 校验中间件（参考文件安全基线第 3 条）。

### 3.6 与 Homebox API 的映射关系

| 自建能力 | Homebox API | 说明 |
|---|---|---|
| 碰一碰拉物品 | `GET /api/v1/locations/{id}/items` | `bind_type=location` 时 |
| 单品详情 | `GET /api/v1/items/{id}` | `bind_type=item` 时 |
| 位置树 | `GET /api/v1/locations` | 激活时展示可选位置 |
| 归属校验 | `GET /api/v1/locations/{id}` / `GET /api/v1/items/{id}` | 按 family group 判断 |
| 写扩展字段 | `PATCH /api/v1/items/{id}` → `customFields` | 颜色/用途/材质落这里（第四章） |
| 打标签 | Tag API | `usage_scene` 可同步为 tag 便于筛选 |
| 照片挂接 | Attachment API | companion 已自动完成，本服务不重复 |
| 二维码兜底 | Labelmaker / QR | 打印含 UID 短链的二维码贴 |

### 3.7 统一响应结构与错误码分段

遵循参考文件第四章：`{ code, message, data }`；`0` 成功，`40001-40099` 参数/业务错误，`40101` 未登录，`40301` 越权，`40901` 冲突，`50001` 内部错误。禁止 200 包一切。

### 3.8 数据模型决策：独立映射表（需求侧已确认，D6 收口）

初期选品洞察师曾建议「给物品/位置加 `nfc_uid` 字段 + 唯一索引」，经对齐后**需求侧已主动撤回**——那是技术实现示意而非硬性商业诉求，本方案独立 `nfc_binding` 映射表已完整覆盖其两条真实诉求（UID 一一对应防重复、跨端通用+家人扫码），03 文档 3.2 节已同步澄清不改 Homebox 核心表。下表保留为决策留痕：

| 维度 | 方案 A：给 Homebox 物品/位置表加 `nfc_uid`（已撤回） | 方案 B（本方案，已采纳）：独立 `nfc_binding` 映射表 |
|---|---|---|
| 是否改第三方源码 | **要改 Homebox 的 Item/Location 表与 API** → 与 01 方案"锁定版本、不 fork"策略冲突，升级必冲突 | 完全不改 Homebox，映射表在自建 schema |
| 换绑/解绑留痕 | 单字段无法表达状态机与历史；覆盖写会丢审计 | 状态机 `active/unbound` + `bound_at/unbound_at` + 历史行保留 |
| 一物多贴 / 一贴换物 | 字段是 1:1，多贴需加 JSON 数组，查询要 `LIKE`，无法加唯一约束 | 映射表天然 1:N，唯一索引约束"同一贴同时只有一条 active" |
| 唯一索引诉求 | 可加，但加在 Homebox 表上 | **已有** `CREATE UNIQUE INDEX uq_active_sticker ON nfc_binding(sticker_uid) WHERE status='active'`，功能等价 |
| 二维码兜底 | 需另存字段 | `qr_fallback` 字段已在映射表 |
| 归属/家庭组校验 | 需 join Homebox 权限 | `family_id` 字段本地直接校验 |

**结论**：需求侧已撤回方案 A，独立 `nfc_binding` 映射表（方案 B）为最终决策，**D6 无需团长裁决**。产品侧额外给出两条商业论据支撑该选择：① 03 文档的"3 色分类"家庭装会让用户给同一箱子贴多张不同颜色贴做视觉归类——天然的一物多贴，单字段表达不了；② 换季/搬家复购场景下用户会把贴纸从旧位置改绑到新位置——需要换绑历史可追溯，只有映射表 + 状态机能提供。`UNIQUE(sticker_uid) WHERE status='active'` 部分唯一索引已等价满足防重复绑定诉求（3.5），且不动第三方源码、延续 01 方案"锁定版本不 fork"策略。

---

## 四、AI 识别字段扩展（颜色 / 用途 / 材质）

### 4.1 companion 现有字段盘点（已核实）

名称、数量、厂商、型号、序列号、购买价格、购买渠道、备注、描述、标签、自定义字段、Asset ID（`HBC_AI_OUTPUT_LANGUAGE=Chinese` 已保证中文）。

### 4.2 新增字段定义与标准色卡（对齐 03 文档第六章五字段）

AI 抽取共五字段：**物品名（companion 原有）+ color + usage_scene + category + material（本方案新增四个）**。

| 字段 | 类型 | 取值约束 | 落地位置 | 会员可见性 |
|---|---|---|---|---|
| `name`（物品名） | 字符串 | companion 原生 | Homebox `name` | 免费 + 会员（免费额度内） |
| `color` | 枚举字符串 | 标准色卡 16 色 + 色系（见下） | Homebox `customFields.color` | **仅会员自动填** |
| `usage_scene` | 枚举数组（1-3 个） | 受限枚举：`日常/办公/户外/厨房/卧室/卫浴/收纳/维修/数码/运动/亲子/宠物/纪念/应急/园艺/其他` | `customFields.usage_scene` + 同步 Tag | **仅会员自动填** |
| `category` | 枚举字符串（1 个） | 分类体系：`清洁/药品/文具/工具/数码/厨具/衣物/食品/书籍/运动/纪念品/其他`（对齐 03 文档"类别"字段） | `customFields.category` + 建议 location（需用户确认，不自动改位置树） | **仅会员自动填** |
| `material` | 枚举字符串 | `塑料/金属/木质/织物/玻璃/陶瓷/皮革/纸品/橡胶/复合材料/未知` | `customFields.material` | **仅会员自动填** |

> `category` 与 `usage_scene` 的区别（避免团队混淆）：`category` 是**物品是什么类**（药品/工具），用于自动归位到位置树；`usage_scene` 是**在什么场景用**（应急/户外），用于筛选找物。二者不可互相替代。

**标准色卡（16 色，量化到色系避免自由文本）**：
`黑/白/灰/红/橙/黄/绿/青/蓝/紫/粉/棕/金/银/透明/多色`。Prompt 中强制"从枚举中选择，禁止输出枚举外颜色；无法判断输出 `多色` 或 `未知`"。**理由**：自由文本颜色无法做筛选/搜索，枚举化后可提供"找出所有蓝色物品"的会员增值查询。

### 4.3 给视觉模型的 Prompt 要点

1. **角色与输出**：`你是家庭物品识别助手。仅输出符合给定 JSON Schema 的 JSON，不要任何解释文字。`
2. **强制枚举**：`color 必须从 [16 色] 中选一个；usage_scene 从 [16 场景] 中选 1-3 个；category 从 [12 类] 中选一个；material 从 [11 类] 中选一个。选不出填"未知/其他"。`
3. **字段互斥规则**：`color=多色 时仍需在 color_detail 中列出主色（可选）；透明材质物品 color 优先填"透明"，material 填"玻璃/塑料"；category 与 usage_scene 不得填同一语义词（如都用"户外"），category 描述物品类别，usage_scene 描述使用场景。`
4. **置信度**：每个新增字段附带 `confidence`（0-1），低于 0.6 的字段前端标黄要求用户确认。
5. **中文约束**：沿用 `HBC_AI_OUTPUT_LANGUAGE=Chinese`，所有枚举值中文输出，避免中英混杂。
6. **防幻觉**：`若图片中颜色因光照失真，以物品本体固有色为准；不确定时宁选"未知"，不要猜测。`
7. **归位建议**：`category 只输出类别枚举与 suggested_location 建议（如"厨房/调料区"），不得声称已写入位置树——位置变更必须由用户确认（防 AI 误改家庭数据）。`

### 4.4 结构化 JSON Schema 示例

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["name", "color", "usage_scene", "category", "material"],
  "properties": {
    "name":            { "type": "string", "description": "物品名称" },
    "quantity":        { "type": "integer", "minimum": 1 },
    "manufacturer":    { "type": "string" },
    "model":           { "type": "string" },
    "color":           { "type": "string", "enum": ["黑","白","灰","红","橙","黄","绿","青","蓝","紫","粉","棕","金","银","透明","多色","未知"] },
    "usage_scene":     { "type": "array", "items": { "type": "string", "enum": ["日常","办公","户外","厨房","卧室","卫浴","收纳","维修","数码","运动","亲子","宠物","纪念","应急","园艺","其他"] }, "minItems": 1, "maxItems": 3 },
    "category":        { "type": "string", "enum": ["清洁","药品","文具","工具","数码","厨具","衣物","食品","书籍","运动","纪念品","其他"] },
    "suggested_location": { "type": "string", "description": "建议位置路径，仅建议不自动写入" },
    "material":        { "type": "string", "enum": ["塑料","金属","木质","织物","玻璃","陶瓷","皮革","纸品","橡胶","复合材料","未知"] },
    "confidence":      { "type": "object", "properties": { "color": {"type":"number"}, "usage_scene": {"type":"number"}, "category": {"type":"number"}, "material": {"type":"number"} } },
    "tags":            { "type": "array", "items": { "type": "string" } }
  }
}
```

**单次识别输出示例**
```json
{ "name": "不锈钢保温杯", "quantity": 1, "manufacturer": "膳魔师", "color": "银", "usage_scene": ["日常","户外"], "category": "厨具", "suggested_location": "厨房/水杯区", "material": "金属", "confidence": { "color": 0.91, "usage_scene": 0.84, "category": 0.88, "material": 0.95 }, "tags": ["水杯"] }
```

### 4.5 落到 Homebox 的方式

- 四个新字段写入 Item 的 `customFields`（companion 原生支持自定义字段提取/写入，见 01 方案 1.3；无需改 Homebox 源码），物品名走原生 `name` 字段。
- `usage_scene` 额外同步为 Homebox Tag，让"按场景筛选"可直接用原生 Tag 过滤，不自建查询层；`category` 同步为 Tag 供"按类别找物"。
- `suggested_location` **只做建议展示**：在确认页显示"建议放到 厨房/水杯区"，用户点确认后才调用 Homebox 位置 API 写入，杜绝 AI 擅自改动位置树。
- 低置信度字段（`confidence < 0.6`）在确认页标黄，用户确认后才提交 → 保证数据质量。
- **字段级付费墙**：网关在转发识别结果前，按 `member.level` 过滤——免费用户仅返回 `name`/`quantity` 等基础字段；`color`/`usage_scene`/`category`/`material` 四个字段对免费用户不返回（前端显示"升级会员解锁完整识别"），但**允许手动填写**（对齐 03 文档 4.2 表格与 R5 隐私要求"关闭 AI 仍可手动录入"）。

### 4.6 A/B 决策点 D2：一次提取 vs 后处理小模型

| 方案 | 做法 | 成本 | 优点 | 缺点 |
|---|---|---|---|---|
| **D2-A（推荐）** | 改造 companion 的识别 prompt/schema，一次调用输出全部字段 | 一次视觉调用（当前 $0.019/100 件） | 成本低、字段一致 | companion 是第三方，需 fork 或确认其支持自定义 prompt/schema 配置 |
| **D2-B（备选）** | companion 保持原样；自建"字段增强层"用小模型对同一张图二次提取 3 字段后合并 | 两次调用（约 1.3-1.6×） | 不动第三方、升级无冲突 | 成本高、两次调用延迟叠加 |

**推荐 D2-A**：先确认 companion 是否提供 prompt/schema 自定义配置入口；若支持则零 fork 接入。若不支持，**不 fork 主分支**，改为在 companion 上游加轻量适配层拦截请求、注入扩展 schema（D2-B 的低成本变体，仍是一次调用）。**严禁为了三个字段长期维护 companion fork**——01 方案已把"companion 非官方、升级不兼容"列为风险。

---

## 五、视觉 Token 计量系统

### 5.1 计量单位：对外"次"、对内"token"（A/B 决策点 D3）

- 用户理解"每次拍照识别消耗 1 次"，不理解 token 波动。
- 内部按实际 token 结算，便于成本核算与防滥用。
- 换算：`1 次 = 1 个 VISION_CREDIT`，预扣时冻结 1 credit，结算时按模型实际 token 折算（封顶 1 credit，超出不追加，避免争议）。
- **D3-A 推荐**：按"次"售卖配额，内部 token 仅作成本监控。理由：定价简单、无账单纠纷。
- **D3-B 备选**：按 token 精确计费（高级用户/API 场景）。V1.1 再评估。

### 5.2 扣费时机：预扣 → 结算 → 退还（状态机）

```
[拍照前] 配额检查：account.balance - frozen >= 1 ? 否则拦截
   ↓
[请求发起] 预扣 PREHOLD：balance -= 1, frozen += 1，写流水
   ↓
[companion 返回成功] 结算 SETTLE：frozen -= 1，写流水（实际消耗入账）
   ↓
[companion 失败/超时] 退还 REFUND：frozen -= 1, balance += 1，写流水
```

- **为什么预扣**：防止用户并发发起 N 次识别，全部通过配额检查后余额变负。
- **为什么失败退还**：网络/模型失败不应扣用户钱，这是留存底线。
- **超时兜底**：预扣记录加 `expires_at`（如 10 分钟），定时任务扫描 `status=prehold` 且过期未结算 → 自动退还，防 companion 崩溃导致冻结永久挂账。

### 5.3 配额检查与并发幂等（防重复扣费）

1. **幂等键**：客户端每次拍照生成 `request_id`（UUID v4），`token_ledger(request_id, user_id)` 建**唯一索引**；重复请求直接返回首次结果，不二次扣费（参考文件 API 幂等要求）。
2. **原子预扣**：单条条件更新 `UPDATE token_account SET balance=balance-1, frozen=frozen+1, version=version+1 WHERE user_id=? AND balance-frozen>=1 AND version=?`（乐观锁），影响行数 0 → 返回配额不足或重试。
3. **并发控制**：同一用户识别请求在网关层用 Redis 分布式锁（key=`vision:{user_id}`，TTL 30s）串行化，避免乐观锁在高并发下频繁重试。**Redis 仅用于锁与轻量缓存，不做数据主存**（参考文件"Redis 必须配持久化"要求：此处锁丢失仅导致重复识别，有幂等键兜底，可接受）。
4. **结算/退还幂等**：同样带 `request_id`，状态机流转用 `WHERE status='prehold'` 条件更新，重复回调不重复入账。

### 5.4 账单明细

`GET /api/v1/billing/ledger?page=1&pageSize=20` 返回：时间、类型（赠送/预扣/结算/退还/购买）、数量、业务描述（"识别 不锈钢保温杯"）、关联请求 ID、余额变动前后值。用户可核对每一笔，符合消费透明要求。

### 5.5 会员等级与配额（对齐 03 文档第四章；A/B 决策点 D4）

| 等级 | 月配额（VISION_CREDIT） | 价格（月/季/年） | AI 字段权益 | 成本测算（¥0.0042/次，含 3× 调用放大） | 配额打满毛利率 |
|---|---|---|---|---|---|
| 免费用户 | 10 次/月 | ¥0 | 仅基础（物品名） | ¥0.042/月 | —（获客成本） |
| 个人 AI 会员 | 300 次/月 | ¥12 / ¥30 / **¥98（主推年付）** | 全五字段 + 批量识别 | 打满 ¥1.26/月 | ≈85%（对年付月均 ¥8.2） |
| 家庭 AI 会员 | 1000 次/月，**≤6 成员共享** | ¥25 / ¥68 / **¥198（主推年付）** | 全五字段 + 批量 + 失败优先队列 + 身份标识 | 打满 ¥4.20/月 | ≈75%（对年付月均 ¥16.5） |
| 自托管自带 Key | 不限 | ¥0 | 全字段 | 用户自付 API 费 | 不适用 |

**配额与计费规则（与 03 文档严格一致）**：

1. **月度重置**：每月 1 日 00:00（Asia/Shanghai）定时任务把 `token_account.balance` 重置为 `member.quota_monthly`（个人 300 / 家庭 1000 / 免费 10）。`frozen` 不清零（可能有跨月未结算的预扣，靠 `expires_at` 退还）；家庭共享账户以 `family_id` 为单位**共用一个 balance**，成员各自请求但共享扣减。
2. **超额降级（不阻断核心功能）**：配额用尽后 AI 按钮置灰并显示"手动录入"，Homebox 原生录入/搜索/NFC 碰一碰全部照常可用——对齐 03 文档"绝不让用户付了钱还被卡住"与 Midjourney Relax 降级模式。这是 6.2 前端拦截的**第三态**（见 6.2）。
3. **加购包**：¥1 / 10 次（`purchase` 类型流水写入 `token_ledger`，当月有效、不跨月重置）；上线初期可测 ¥3 / 30 次加购包验证付费意愿（03 文档第九章分阶段建议）。
4. **免费额度策略**：10 次刻意"够体验、不够整理全屋"（一个收纳箱约 20~50 件），形成升级动机——这是配额数值的业务依据，研发不得随意调大。

> **诚实结论（与 03 文档 5.3 一致）**：Token 是**计量单位，不是定价依据**。即使重度用户打满配额，成本也只占会员费 15~25%。计量的真实目的是（1）会员权益分层，（2）防滥用刷接口，（3）为更高成本模型预留框架。**严禁营销宣称"AI 成本高、亏本补贴"**（03 文档反模式警告）——家庭用量月成本 <¥1.5，用户识破后信任反噬比不收费更糟。

- **D4-A 推荐**：按 03 文档三级体系（免费 10 / 个人 300 / 家庭 1000 共享），主推年付。
- **D4-B 备选**：按贴纸销量赠送配额（买 10 张贴送 50 次），把实体耗材与数字权益捆绑，强化 Tom 要的"用户粘性"。**建议与 D4-A 叠加实施**（需在 `token_ledger` 增加 `biz_type='sticker_promo'` 来源标识）。

### 5.6 五张表字段级设计（核心，遵循参考文件第三章）

```sql
-- 1. 会员权益：member（只存权益，不存任何支付渠道信息——与 product-scout 解耦建议对齐）
CREATE TABLE member (
  id                    BIGSERIAL PRIMARY KEY,
  user_id               BIGINT NOT NULL UNIQUE,
  family_id             BIGINT,                           -- 家庭会员所属组；个人/免费为 NULL
  level                 VARCHAR(16) NOT NULL DEFAULT 'free', -- free|personal|family|self_hosted（对齐 03 文档）
  quota_monthly         INT NOT NULL DEFAULT 10,           -- 10 / 300 / 1000
  price_monthly_cents   INT NOT NULL DEFAULT 0,            -- 金额一律整型分，禁浮点
  price_quarter_cents   INT NOT NULL DEFAULT 0,
  price_year_cents      INT NOT NULL DEFAULT 0,
  cycle_start           DATE NOT NULL,
  cycle_end             DATE NOT NULL,
  status                VARCHAR(16) NOT NULL DEFAULT 'active', -- active|expired|refunded
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at            TIMESTAMPTZ
);
CREATE INDEX idx_member_user ON member(user_id);
CREATE INDEX idx_member_family ON member(family_id) WHERE family_id IS NOT NULL;

-- 2. Token 账户：token_account（家庭版以 family_id 共享一个余额）
CREATE TABLE token_account (
  id               BIGSERIAL PRIMARY KEY,
  user_id          BIGINT,                        -- 个人/免费账户归属
  family_id        BIGINT,                        -- 家庭账户归属（与 user_id 二选一）
  balance          INT NOT NULL DEFAULT 10,       -- 可用余额
  frozen           INT NOT NULL DEFAULT 0,        -- 预扣冻结
  lifetime_granted INT NOT NULL DEFAULT 0,
  lifetime_used    INT NOT NULL DEFAULT 0,
  version          INT NOT NULL DEFAULT 0,        -- 乐观锁
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_acct_user ON token_account(user_id) WHERE family_id IS NULL;
CREATE UNIQUE INDEX uq_acct_family ON token_account(family_id) WHERE family_id IS NOT NULL;

-- 3. Token 流水：token_ledger（冷热分离，按月归档）
CREATE TABLE token_ledger (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL,
  account_id    BIGINT NOT NULL,
  request_id    UUID NOT NULL,                 -- 幂等键
  type          VARCHAR(16) NOT NULL,          -- grant|prehold|settle|refund|purchase
  amount        INT NOT NULL,                  -- 有符号：+赠送/退还，-预扣
  biz_type      VARCHAR(32) DEFAULT 'ai_vision',
  biz_id        VARCHAR(128),                  -- Homebox item id 或识别任务 id
  before_bal    INT NOT NULL,
  after_bal     INT NOT NULL,
  status        VARCHAR(16) NOT NULL DEFAULT 'done', -- done|expired
  expires_at    TIMESTAMPTZ,                   -- prehold 超时退还
  remark        VARCHAR(256),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, request_id, type)           -- 防重复扣费核心
);
CREATE INDEX idx_ledger_user_time ON token_ledger(user_id, created_at DESC);
CREATE INDEX idx_ledger_expire ON token_ledger(status, expires_at) WHERE status='prehold';

-- 4. NFC 贴纸库存：nfc_sticker
CREATE TABLE nfc_sticker (
  id                BIGSERIAL PRIMARY KEY,
  uid               VARCHAR(16) NOT NULL UNIQUE,  -- 7-byte 十六进制
  activation_code   VARCHAR(64) NOT NULL,         -- bcrypt 哈希
  batch_no          VARCHAR(32) NOT NULL,
  chip_type         VARCHAR(16) DEFAULT 'NTAG213',
  status            VARCHAR(16) NOT NULL DEFAULT 'manufactured', -- manufactured|shipped|activated|bound|retired
  owner_user_id     BIGINT,
  activated_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ
);
CREATE INDEX idx_sticker_batch ON nfc_sticker(batch_no);

-- 5. 绑定关系：nfc_binding
CREATE TABLE nfc_binding (
  id           BIGSERIAL PRIMARY KEY,
  sticker_uid  VARCHAR(16) NOT NULL,
  user_id      BIGINT NOT NULL,
  family_id    BIGINT NOT NULL,                 -- 归属校验依据
  bind_type    VARCHAR(16) NOT NULL,            -- location|item
  bind_id      VARCHAR(64) NOT NULL,            -- Homebox ID
  status       VARCHAR(16) NOT NULL DEFAULT 'active', -- active|unbound
  qr_fallback  VARCHAR(256),
  bound_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  unbound_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_active_sticker ON nfc_binding(sticker_uid) WHERE status='active';
CREATE INDEX idx_binding_user ON nfc_binding(user_id, status);

-- 6. 支付订单：payment_order（新增第 6 张表，权益/配额与支付渠道解耦，见 6.5）
CREATE TABLE payment_order (
  id                BIGSERIAL PRIMARY KEY,
  order_no          VARCHAR(64) NOT NULL UNIQUE,          -- 自有订单号
  user_id           BIGINT NOT NULL,
  family_id         BIGINT,                              -- 家庭会员购买时关联
  product_code      VARCHAR(64) NOT NULL,                -- personal_year|family_year|credit_10 等，与渠道商品 ID 解耦
  amount_cents      INT NOT NULL,                        -- 金额按分
  currency          VARCHAR(8) NOT NULL DEFAULT 'CNY',
  pay_channel       VARCHAR(16) NOT NULL,                -- wechat|alipay|apple_iap|h5|manual
  channel_order_no  VARCHAR(128),                        -- 渠道订单号/IAP transaction_id
  status            VARCHAR(16) NOT NULL DEFAULT 'pending', -- pending|paid|refunded|closed
  paid_at           TIMESTAMPTZ,
  callback_payload  JSONB,                               -- 原始回调，对账用
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_order_user ON payment_order(user_id, created_at DESC);
CREATE UNIQUE INDEX uq_channel_order ON payment_order(pay_channel, channel_order_no) WHERE channel_order_no IS NOT NULL;
```

**设计自检**（对照参考文件第三章）：✅ 时间戳三件套 + 软删除；✅ 状态机显式枚举；✅ 金额 `*_cents` 整型分；✅ 幂等唯一索引；✅ 索引覆盖高频查询；✅ 流水表预留按月归档；✅ 扩展只预留已明确方向（`family_id` 对应 03 文档的家庭共享，"≤6 人"上限在业务层校验）。

> **关于"5 张表"与新增第 6 张**：任务基线要求账户/流水/会员/贴纸/绑定关系 5 张，本方案额外增加 `payment_order` 是落实 product-scout「权益/配额与支付渠道解耦」的明确建议——换收银台时只改 `pay_channel` 分支与回调适配，不动会员与计量模型。这是有理由的复杂度，非过度设计。

---

## 六、会员鉴权与付费墙

### 6.1 鉴权链路（App / 小程序 → 网关 → 会员服务）

```
[App/小程序] 拍照 → 带 JWT 请求 POST /api/v1/vision/recognize
      ↓
[API 网关] ① 验 JWT ② 查 member.level/quota ③ 预扣 token (PREHOLD)
      ↓  ④ 注入内部头 X-Internal-Token（短时签名，防绕过网关直连 companion）
[会员服务/计量服务] 记录流水、配额判定
      ↓
[companion :8000] 只做 AI 识别，看不到会员概念；受 HBC_RATE_LIMIT_* 兜底限流
      ↓
[网关] 收到结果 → SETTLE 或 REFUND → 返回 App
```

关键点：**companion 不暴露到公网**，只接受来自网关的内部请求（Docker 网络隔离 + `X-Internal-Token` 校验）。`HBC_HOMEBOX_API_KEY`、`HBC_LLM_API_KEY` 始终坚持在服务端（01 方案口径），不下发浏览器/小程序。

### 6.2 前端拦截点（三态，体验优先；对齐 03 文档"超额不阻断"）

进入拍照页先 `GET /api/v1/billing/quota` → 返回 `{ balance, level, quota_monthly, reset_at, shared_by_family }`。按余额分三态：

1. **第一态（余额 ≥4）**：正常放行。免费用户隐藏四个扩展字段的自动填充位（见 4.5），仅自动填物品名。
2. **第二态（1 ≤ 余额 ≤ 3）**：正常放行，但结算页软提示"本月还剩 X 次，个人会员 300 次/月"——不阻断当前操作，不制造焦虑。
3. **第三态（余额 = 0）——降级不阻断**：AI 拍照按钮置灰显示"本月配额已用完，可升级会员或购买加购包（¥1/10 次）"；**同时「手动录入」入口常亮**，用户仍可用 Homebox 原生表单完成登记。这是 03 文档「绝不让用户付了钱还被卡住」与 Midjourney Relax 模式的落点——**超额只关 AI，不关产品**。免费用户文案改为"免费 10 次已用完，升级解锁 300 次/月 + 全字段识别"。

补充两处：

4. **失败退还提示**：识别失败自动退还后 Toast"识别失败，已退还本次次数"——透明化建立信任。
5. **家庭共享提示**：家庭会员成员使用共享额度时，弹层显示"当前使用家庭共享额度（剩余 X/1000）"，避免成员互相消耗产生困惑。

### 6.3 companion 侧限流配合

- companion 已有 `HBC_RATE_LIMIT_*` 环境变量（已核实事实），网关预扣通过后转发请求，companion 侧配置**兜底速率限制**：如 `HBC_RATE_LIMIT_ENABLED=true`、`RATE_LIMIT_PER_MINUTE=60`（按用户 ID 维度由网关透传），防止网关被绕过或逻辑 bug 导致刷爆 AI 账单。
- 双层防护：网关做**业务级配额**（按会员等级），companion 做**技术级限流**（按频率）。任一层触发都拒绝，返回统一 `429 QUOTA_EXCEEDED` / `429 RATE_LIMITED`。

### 6.4 多端合规（逐端核对，不可模糊）

| 端 | 付费合规要求 | 规避方案 |
|---|---|---|
| **iOS App** | 虚拟商品（会员配额、Token）内购**必须走 IAP**，苹果抽成 15-30%；诱导外链支付会被拒 | 会员订阅用 StoreKit/IAP，`iap_product_id` 落 `member` 表；**实体 NFC 贴走普通支付（可外链电商）**——实体商品不受 IAP 约束，这正是"卖贴纸"比"卖会员"更划算的隐藏逻辑 |
| **安卓 App** | 虚拟支付可用微信/支付宝 | 走自有支付网关，无 IAP 限制 |
| **微信小程序** | iOS 端小程序虚拟支付受限；类目资质要求 | 小程序**只做查询与扫码，不做会员购买**；购买引导至 App 或公众号 H5；小程序内 AI 识别功能对 iOS 用户降级为只读/引导 App |
| **鸿蒙（V1.1）** | 华为 IAP + AGC 隐私规范 | V1.0 不做；V1.1 按 ArkTS 独立适配，支付走华为 IAP |

> **iOS 审核特别提示**：隐私清单 PrivacyInfo 需声明相机/相册/NFC 用途；`NFCReaderUsageDescription` 文案写清"用于读取物品贴纸"；App 描述必须与实际功能一致（我们说"绑定"不说"写入芯片"，见 1.4）。

> **合规前置（🟡 需 Tom 确认，03 文档一票否决项）**：收会员费/贴纸款需**微信支付或支付宝商户号**，主体须为个体户/公司——**个人开发者无法开通微信支付商户号**。此项未定，收银台无法开工。但按 6.5 解耦设计，权益/计量模块可先行开发，商户号只影响支付适配层。

> **隐私授权（03 文档 R5）**：拍照识别前弹窗告知"照片将上传云端用于 AI 识别"，用户同意后才上传；提供"关闭 AI 仍可手动录入"选项（与超额降级同一入口）；家庭数据按 `family_id` 隔离；隐私政策含未成年人条款。

### 6.5 权益/配额与支付渠道解耦（落实 product-scout 建议）

三层分离，换收银台不动核心模型：

```
用户支付 → payment_order(pay_channel=wechat|alipay|apple_iap|h5, product_code=personal_year|family_year|credit_10)
        → 支付回调验签（幂等：按 channel_order_no 唯一索引去重）
        → 仅更新 member.level / cycle_end，并写 token_ledger(type='grant')
        → 权益生效，计量服务按新 quota_monthly 运行
```

- `product_code` 是**渠道无关的内部商品码**；渠道商品 ID（IAP product id、微信支付模板）留在支付适配层配置，不进 `member` 表（已移除原 `iap_product_id` 字段）。
- 换收银台（如微信→支付宝、新增 H5 收银台）只增 `pay_channel` 分支与回调适配器，会员表与计量表零改动。
- 支付回调必须幂等（参考文件第三方选型注意项）：`UNIQUE(pay_channel, channel_order_no)` 已建。

### 6.6 自托管兼容模式

自托管用户可填自己的 `HBC_LLM_API_KEY`，系统标记 `member.level=self_hosted`，跳过配额检查——既不失去这类用户，又不承担他们的 API 成本。同时满足 03 文档 R5"可本地处理优先"的隐私诉求。

---

## 七、技术选型总表（本轮新增能力，逐项给理由）

| 层 | 选型 | 选择理由（对照明细） |
|---|---|---|
| NFC 芯片 | NTAG213 预编码 UID（增强款 NTAG215） | 成本最低、UID 全球唯一锁定、容量够 UID-only 方案；跨端通用（对比表见 1.3） |
| NFC 绑定服务 | Node/Express + PostgreSQL（沿用 01 的 Homebox PG，独立 schema） | 与 01 技术栈一致、团队可维护；升级自 SQLite 是因付费/并发需要事务与唯一约束（见 0.2） |
| AI 层 | homebox-companion（Python/FastAPI + LiteLLM），不 fork | 拍照识别现成；扩展字段走 prompt/schema 注入而非改源码（见 4.6） |
| 会员/计量 | 自建模块（模块化单体）+ Redis 锁 | 日活千级无需微服务；Redis 只做锁，数据主存 PG，符合参考文件 |
| 支付 | 微信/支付宝（安卓/H5）+ Apple IAP（iOS 会员） | 合规硬要求；回调必须幂等（参考文件第三方选型注意项） |
| App | Flutter（沿用 01）+ `nfc_manager` | 一套代码双端；NFC 用插件，平台差异由适配层隔离 |
| 小程序 | Taro/uni-app（沿用 01），只读 + 扫码 | 家人免安装入口；不做会员购买规避 iOS 虚拟支付限制 |
| 网关 | Caddy（自动 HTTPS）沿用 01 | 统一鉴权/证书/CORS，承载付费墙拦截 |

**反向声明（反过度设计）**：本方案**不引入**微服务、Kafka/RabbitMQ、K8s、多级缓存、分库分表。计费流水用 PG 事务 + 定时归档即可；Redis 仅一把锁。日活破万再评估拆分（参考文件演进路径）。

---

## 八、系统架构与模块划分（更新版）

```
[App Flutter]  [小程序 Taro]
      │ HTTPS   │ HTTPS
      └───┬─────┘
          ▼
   [API 网关 Caddy]  ← JWT 鉴权 + 会员配额检查 + Token 预扣 + 限流
          │
    ┌─────┼──────────┬─────────────┐
    ▼     ▼          ▼             ▼
 [会员/  [NFC 绑定  [Homebox :7745] [companion :8000]
 计量]   服务]       物品/位置/标签   AI 识别/AI Chat
    │     │          │             │ (LiteLLM→GPT, HBC_RATE_LIMIT_*)
    └─────┴────┬─────┴─────────────┘
               ▼
        [PostgreSQL]  ← schema: homebox / nfc_saas / billing
               │
        [Redis]  ← 仅分布式锁 + 短时缓存
        [对象存储] ← 照片直传 + CDN
        [支付网关] ← 微信/支付宝/IAP 回调
```

**模块依赖（禁止循环）**：`gateway → {member, nfc-binding, billing} → {homebox, companion} → postgres`。member 与 nfc-binding 互不依赖；billing 单向依赖 member；companion 不反向调用任何自建服务。

---

## 九、非功能性承诺（对齐参考文件第七章，给具体数值）

| 维度 | 承诺值 | 验收方式 |
|---|---|---|
| 并发 | 支持 100-500 并发在线；单用户识别串行化（Redis 锁 TTL 30s） | 压测 500 并发 resolve 接口 |
| 响应 | 核心 API（activate/binding/resolve）P95 ≤ 500ms；AI 识别端到端 P95 ≤ 8s（含模型 ~3.4s）；首屏 ≤ 2s（4G） | APM 监控 |
| 可用性 | 月度 ≥ 99.5% | 云监控 SLO |
| 崩溃率 | App ≤ 0.1% | 埋点上报 |
| 安全 | 全站 HTTPS、bcrypt 存激活码、接口鉴权全覆盖、owner 校验 100%、密钥走环境变量/KMS、审计日志留存 ≥6 个月 | 安全扫描 + 代码审计 |
| 备份 | PostgreSQL 每日自动备份 + 保留 ≥7 天；`token_ledger` 按月归档 | 运维方案对齐 |
| 计费准确性 | 重复扣费率 = 0（唯一索引 + 乐观锁）；失败退还成功率 ≥ 99.9% | 对账任务每日校验 |

---

## 十、技术风险 Top3（触发条件 + 预案）

> 说明：本表只列**技术风险 Top3**。商业侧风险（R1 付费转化 / R2 贴纸履约毛利 / R4 Token 成本波动 / R5 隐私）见 `03-商业模式与会员体系.md` 第八章，本方案在 6.4（合规与隐私）、5.5（诚实成本结论）、6.5（多模型路由预留）中做了技术侧承接。

| # | 风险 | 触发条件 | 预案 |
|---|---|---|---|
| 1 | **companion 升级破坏扩展字段** | companion 发新版本，prompt/schema 注入失效 | 锁定镜像 tag（不用 latest，01 方案已列此风险）；CI 加"扩展字段识别"回归用例；失败自动降级到 D2-B 后处理层，用户无感 |
| 2 | **iOS 审核拒绝（IAP / NFC 描述不符）** | 会员购买走外链支付；文案写"写入芯片" | 会员 IAP 化（`iap_product_id`）；文案统一"绑定"；提前准备 PrivacyInfo 与权限用途说明；预留 2 周审核缓冲 |
| 3 | **Token 重复扣费/冻结挂账引发投诉** | 并发高压下乐观锁重试失败；companion 崩溃导致 prehold 不结算 | 幂等唯一索引 + 条件更新；`expires_at` 定时扫描 10 分钟自动退还；每日对账任务校验 `balance+frozen` 与流水一致性，异常告警 |

---

## 十一、MVP 范围（当期必须 vs 可延后 + 理由）

### 11.1 V1.0 必须做（本轮新增部分）

1. ✅ **NTAG213 UID-only 预编码贴 + 激活码体系**——能卖的技术前提，不做则整个商业模式不成立。
2. ✅ **三端 UID 读取 + 云端绑定 + 碰一碰查询（≤4 步）**——Tom 需求 1 的核心体验。
3. ✅ **NFC 绑定服务 6 个 API + 6 张表**——含防冒领/归属校验，安全底线不能延后。
4. ✅ **物品名/颜色/用途/类别/材质五字段 + 标准色卡 + JSON Schema**——Tom 需求 2 的核心，且需同步进会员权益才有差异化；免费用户仅返回物品名（4.5 字段级付费墙）。
5. ✅ **Token 预扣/结算/退还 + 幂等 + 月度重置 + 免费 10 次额度 + ¥3/30 次加购包 + 付费墙三态拦截（含超额降级手动录入）**——不计量则 AI 成本无上限、无法防滥用。按 03 文档第九章「先跑通单次付费价值」策略，V1.0 先上轻量加购包验证付费意愿，不上完整订阅。
6. ✅ **支付渠道解耦骨架（payment_order + 回调幂等）+ iOS 内购通道 + 小程序购买引导跳转**——架构解耦先行，商户号未定也能开发权益/计量；iOS 虚拟商品必须 IAP，实体贴纸走普通支付。

### 11.2 可延后

- ⏳ **会员订阅（月 ¥12/季 ¥30/年 ¥98）与家庭版（1000 次共享、≤6 人）**——**V1.1**，依据 03 文档第九章"先卖 ¥3/30 次加购包验证付费意愿，再上订阅与家庭版"。表结构已预留 `family_id`、`price_*_cents`、`level=family`，届时零迁移。
- ⏳ **安卓 NDEF 短链写入增强（NTAG215）**——UID-only 已满足核心体验，NDEF 只是锦上添花；延后到 V1.1，理由：多一条写入失败路径就多一类售后。
- ⏳ **鸿蒙 App 适配**——ArkTS 需独立工程，用户基数与投入不匹配，V1.1 再评估（01 方案也未列鸿蒙为当期）。
- ⏳ **按 token 精确计费（D3-B）**——"按次"已够用，精确计费增加账单纠纷，V1.1 观察。
- ⏳ **买贴纸送配额（D4-B 叠加）**——依赖电商系统对接，V1.0 先人工发码，跑通后再自动化。
- ⏳ **本地视觉模型**——隐私优先用户诉求，01 方案已延后，本轮不变。
- ⏳ **AI Chat 高级会员开放**——companion 已有 24 工具，但鉴权链路复杂，V1.1 随会员体系成熟后开。

---

## 十二、A/B 决策点汇总（请团长/Tom 拍板）

| 编号 | 决策点 | 选项 A（推荐） | 选项 B | 影响 |
|---|---|---|---|---|
| **C1** | 项目性质 | SaaS 主形态（本文口径） | 纯自托管 + 第三方卖贴纸 / 降级为爱好项目 | 对应 03 文档第九章备选；影响第六、十一章；需团长先确认 |
| **D1** | NFC 芯片 | NTAG213 UID-only | NTAG215 带短链 NDEF | 成本 vs 安卓体验增强（03 文档 SKU：体验/家庭/大包装用 213，个性款用 215） |
| **D2** | 扩展字段实现 | prompt/schema 注入（一次调用） | 后处理小模型（二次调用） | 成本 1× vs 1.3-1.6× |
| **D3** | 计量单位 | 按"次"对外、token 内控 | 按 token 精确计费 | 账单复杂度 |
| **D4** | 会员档位 | 按 03 文档三级（10/300/1000 共享）+ 买贴送配额叠加 | 仅三级，不加赠 | 粘性钩子强度；档位数值已锁定，仅决策是否叠加赠配额 |
| **D5** | AI 供应商 | 沿用 GPT-5.6 Luna（$0.019/100） | 切国内视觉模型（DeepSeek/通义） | 合规/成本/延迟（03 文档 R4 多模型路由保险） |
| **D6** | UID 数据模型 | **独立 `nfc_binding` 映射表（3.8，最终决策）** | 给 Homebox 加 `nfc_uid` 字段（需求侧已撤回） | ✅ **已收口无需裁决**：03 文档 3.2 节已同步，选 B 避免 fork 且支持一物多贴/换绑审计 |
| **D7** | 分期策略 | V1.0 先 ¥3/30 次加购包 + 体验装贴纸，V1.1 上订阅/家庭版（03 文档口径） | V1.0 直接上完整订阅 | 验证付费意愿的速度 vs 一期工作量 |

> **一票否决前置（非技术决策，但阻塞收银台开发）**：🟡 商户号/经营主体（个体户或公司）、iOS 虚拟支付路径——见 03 文档第九章。技术侧已通过 6.5 解耦做到"商户号未定也可先开发权益/计量"。

---

## 十三、多端适配核对表（逐条对照参考文件第五章）

| 端 | 核对项 | 本方案措施 |
|---|---|---|
| iOS | 隐私清单 PrivacyInfo + 权限用途文案 | 声明 NFC/相机/相册用途；`NFCReaderUsageDescription` |
| iOS | 虚拟商品走 IAP | 会员配额 IAP 化；实体贴纸走普通支付 |
| iOS | 功能与描述不符 | 文案"绑定"非"写入芯片" |
| iOS | Sign in with Apple | 若接第三方登录则支持（会员体系预留） |
| 微信小程序 | 主包 ≤2MB / 整包 ≤30MB | 小程序只做只读+扫码，逻辑轻，静态资源 CDN |
| 微信小程序 | 域名白名单备案 + HTTPS | 网关域名提前备案配置 |
| 微信小程序 | iOS 虚拟支付受限 | 不在小程序卖会员，引导 App |
| 微信小程序 | 基础库梯度降级 | NFC 不可用时统一二维码兜底 |
| 鸿蒙 | ArkTS 禁 any / UIAbility 生命周期 | V1.1 独立适配，不复用 Android 代码 |
| Web | 首屏 FCP ≤2s | 后台/会员页静态资源 CDN |
| 全端 | 金额按分、鉴权全覆盖、审计日志 | 5 张表设计已落实 |

---

**本次产出完毕。可继续深化方向**：
1. 输出 NFC 绑定服务 + 会员计量服务的完整 OpenAPI 3.0 文件与 Flutter `nfc_manager` 激活/绑定代码骨架（含错误重试与 UI 三态状态机）。
2. 针对决策点 C1（SaaS vs 自托管）与 D7（加购包先行 vs 订阅一步到位）做成本/收益/运维投入的 AB 对比测算，附「加购包 → 订阅」付费转化敏感性分析。

[技术研发方案]
