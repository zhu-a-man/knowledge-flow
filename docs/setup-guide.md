# KnowledgeFlow 部署手册

从零到一完整跑通：Railway 部署 → PostgreSQL 数据库 → DeepSeek API → OpenClaw 接入。

---

## 准备工作

需要注册以下三个账号（全部免费，DeepSeek 充值10元可用数月）：

| 账号 | 用途 | 地址 |
|------|------|------|
| GitHub | 托管代码，Railway 从这里部署 | https://github.com |
| Railway | 云端运行服务（免费额度够个人用） | https://railway.app |
| DeepSeek | AI 提取知识（国内直连，推荐） | https://platform.deepseek.com |

---

## 第一步：Fork 代码到自己的 GitHub

1. 打开 https://github.com/your-username/knowledge-flow
2. 点击右上角 **Fork** → 创建到自己账号下
3. 你现在有了 `你的用户名/knowledge-flow` 这个仓库

---

## 第二步：在 Railway 部署服务

### 2.1 创建 Railway 项目

1. 登录 [Railway](https://railway.app)
2. 点击 **New Project** → **Deploy from GitHub repo**
3. 授权 Railway 访问你的 GitHub 仓库
4. 选择 `knowledge-flow` 仓库 → 点击 Deploy

> ⚠️ 如果找不到仓库，点击"Configure GitHub App"给 Railway 授权访问你的 repo。

### 2.2 添加 PostgreSQL 数据库（必须做，否则数据会丢）

> ⚠️ Railway 的容器每次部署都会重置，如果不加数据库，数据随时会消失。

1. 在 Railway 项目主页，点击右上角 **+ Add** → **Database** → **PostgreSQL**
2. 等待数据库启动（显示 Online 即可）
3. 进入 `knowledge-flow` 服务 → **Variables** 标签
4. 看到提示 "Trying to connect a database? **Add Variable**"，点击 **Add Variable**
5. 选择 `DATABASE_URL`，确认添加

> ⚠️ PostgreSQL 和 knowledge-flow 必须在**同一个 Railway 项目**里，跨项目不会自动注入 DATABASE_URL。

### 2.3 设置环境变量

在 knowledge-flow 服务的 **Variables** 标签里，点击 **+ New Variable** 添加：

| 变量名 | 值 | 说明 |
|--------|----|------|
| `DEEPSEEK_API_KEY` | `sk-xxx...` | DeepSeek API Key |
| `KF_API_KEY` | 自定义字符串（如 `kf_abc123`） | API 鉴权密钥（个人用可不填） |

> `DATA_DIR` 变量现在**不需要设置**，已改用 PostgreSQL 存储，不再依赖文件系统。

### 2.4 确认部署成功

1. 进入 `knowledge-flow` 服务 → **Deployments** 标签
2. 看到最新部署显示 **Deployment successful** ✓
3. 点击服务域名（如 `knowledge-flow-xxx.up.railway.app`）
4. 能打开页面、看到"KnowledgeFlow"标题，说明部署成功

记下你的服务地址，后面配置 OpenClaw 会用到。

---

## 第三步：获取 DeepSeek API Key

1. 注册 [DeepSeek Platform](https://platform.deepseek.com)
2. 进入 **API Keys** → **Create API Key** → 复制 Key（`sk-xxx` 开头）
3. **充值**：进入充值页面，充值 10 元（约够处理几千篇文章）
4. 将 Key 填入 Railway 的 `DEEPSEEK_API_KEY` 变量

> **为什么推荐 DeepSeek？**
> - 国内直连，不需要代理
> - 费用约 ¥0.002/篇（Claude 贵5倍）
> - 效果与 Claude 相当

**备选方案：**
- **通义千问**（阿里云）：注册有免费额度，将 `DASHSCOPE_API_KEY` 填入，并修改 `ai_processor.py` 顶部的 `PROVIDER` 配置
- **Claude**：需能访问 api.anthropic.com，修改 `PROVIDER` 配置

---

## 第四步：接入 OpenClaw（微信龙虾机器人）

### 4.1 确认微信已接入 OpenClaw

在终端运行：
```bash
npx -y @tencent-weixin/openclaw-weixin-cli@latest install
```
扫码绑定后，微信里会出现"微信 ClawBot"联系人。

> 如果你使用的是公司/团队自建的龙虾平台，跳到 4.3。

### 4.2 安装技能

将项目里的 `skill.md` 内容复制到你的龙虾平台的"技能中心"，填入以下两个变量：

| 变量 | 填写内容 |
|------|---------|
| `KF_BASE_URL` | 你的 Railway 服务地址，如 `https://knowledge-flow-xxx.up.railway.app` |
| `KF_API_KEY` | 你在 Railway 设置的 KF_API_KEY（没设置则填空） |

### 4.3 测试是否跑通

向微信 ClawBot 发送一条公众号文章链接，如：
```
https://mp.weixin.qq.com/s/xxxxxx
```

正常回复格式：
```
✅ 已保存到知识库

📌 AI工具 › 编程助手
💡 几个工具装上去效率翻倍
...
```

然后打开 `https://你的域名.railway.app/view`，应该能看到刚才保存的内容。

---

## 常见问题

### 部署成功但访问页面报错

检查 Railway Deployments 日志，常见原因：
- `DEEPSEEK_API_KEY` 未设置或余额为零 → 添加变量或充值
- `DATABASE_URL` 未注入 → 重新按第 2.2 步操作

### 公众号链接提取失败

微信公众号分两种：
- **公开文章（无需关注）**：成功率约 70%，可正常提取
- **需要关注/已删除**：无法提取，龙虾会提示"把正文复制出来发给我"

这是微信的限制，不是 bug。提示用户复制正文即可。

### 数据每次部署后丢失

说明 `DATABASE_URL` 没有正确配置。按第 2.2 步重新检查：
1. PostgreSQL 和 knowledge-flow 是否在同一个 Railway 项目
2. knowledge-flow 的 Variables 里是否有 `DATABASE_URL`

### DeepSeek 提示"余额不足"

去 DeepSeek 后台充值，最低10元。每次处理一篇文章约消耗 ¥0.002。

### 想切换到其他 AI 模型

修改 `ai_processor.py` 文件顶部的配置，改完后 push 到 GitHub，Railway 自动重新部署：

```python
# 切换到通义千问
PROVIDER = "qwen"
API_KEY_ENV = "DASHSCOPE_API_KEY"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
TEXT_MODEL = "qwen-plus"
VISION_MODEL = "qwen-vl-plus"
```

---

## 验证一切正常的 Checklist

```
- [ ] Railway 部署显示 "Deployment successful"
- [ ] 访问 /view 页面能正常打开
- [ ] Variables 里有 DATABASE_URL、DEEPSEEK_API_KEY
- [ ] 向龙虾发一条链接，收到正常回复
- [ ] /view 页面出现刚保存的内容
- [ ] 再次发同一条链接，显示"已更新"而不是重复保存
```
