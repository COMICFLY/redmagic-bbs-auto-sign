# RedMagic Auto Sign

红魔社区自动签到脚本，使用社区 H5 接口完成签到、转盘和宝箱领取。脚本只读取配置好的社区 `accessToken`，不处理账号密码或短信验证码。

## 功能

- 每日签到/状态查询：`points/home/index`
- 转盘抽奖：`points/prize/launch`，10 次，间隔 1.5 秒
- 宝箱领取：`points/home/openbox`
- 支持单账号 token、多账号 token、JSON 多账号
- 支持 GitHub Actions 定时运行
- 宝箱工作流每 30 分钟检查一次，到时间才领取
- 支持 PushPlus、Server 酱、Bark、Telegram、自定义 Webhook 推送

## 文件结构

```text
redmagic-auto-sign/
  redmagic_auto_sign.py
  .env.example
  .github/workflows/redmagic-auto-sign.yml
  .github/workflows/redmagic-box.yml
```

## GitHub Actions 配置

把本目录推到 GitHub 仓库后，进入：

`Settings` -> `Secrets and variables` -> `Actions`

在 `Repository secrets` 里添加 token。

### 单账号

| Secret | 说明 |
| --- | --- |
| `REDMAGIC_ACCESS_TOKEN` | 红魔社区请求头里的 `accessToken` |

### 多账号

多个 token 可以放在 `REDMAGIC_ACCESS_TOKENS`，一行一个，也支持逗号或分号分隔。

| Secret | 说明 |
| --- | --- |
| `REDMAGIC_ACCESS_TOKENS` | 多个红魔社区 `accessToken` |

也可以使用 JSON：

```json
[
  {"name": "main", "access_token": "token1"},
  {"name": "alt", "access_token": "token2"}
]
```

把它保存为 `REDMAGIC_ACCOUNTS`。

## 推送配置

下面任意配置一个或多个即可：

| Secret | 推送渠道 |
| --- | --- |
| `PUSHPLUS_TOKEN` 或 `PUSH_PLUS_TOKEN` | PushPlus |
| `SCT_KEY` 或 `SERVERCHAN_SENDKEY` | Server 酱 Turbo / Server 酱³ |
| `BARK_KEY` 或 `BARK_URL` | Bark |
| `TG_BOT_TOKEN` + `TG_USER_ID` | Telegram |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Telegram |
| `REDMAGIC_WEBHOOK_URL` | 自定义 Webhook，POST JSON |

Server 酱的 Secret 只填写 SendKey，不要填写完整 API 地址。`SCT` 开头的 key 使用 Turbo，`sctp` 开头的 key 使用 Server 酱³，脚本会自动选择对应接口。

## 可选变量

这些放在 `Settings` -> `Secrets and variables` -> `Actions` -> `Variables` 更合适：

| Variable | 默认值 | 说明 |
| --- | --- | --- |
| `REDMAGIC_ENABLE_BOX` | `false` | 主签到工作流是否顺带领宝箱；启用独立宝箱工作流后建议保持 `false` |
| `REDMAGIC_BOX_PUSH_ONLY_OPENED` | `true` | 独立宝箱工作流只在真正领取到宝箱时推送 |
| `REDMAGIC_ENABLE_LOTTERY` | `true` | 是否抽转盘 |
| `REDMAGIC_LOTTERY_TIMES` | `10` | 转盘次数 |
| `REDMAGIC_LOTTERY_DELAY` | `1.5` | 转盘间隔秒数 |

## 宝箱工作流

宝箱在领取成功后约 4 小时刷新。GitHub Actions 的 cron 可能会延迟几分钟启动，如果严格每 4 小时跑一次，可能刚好早于 `nextOpenTime` 执行，然后错过一轮。

仓库包含独立宝箱工作流 `.github/workflows/redmagic-box.yml`，每 30 分钟运行一次：

```bash
python redmagic_auto_sign.py --box-only
```

这个模式会先查 `nextOpenTime` / `boxWaitingOpen`，只有可领取时才调用 `points/home/openbox`。`REDMAGIC_BOX_PUSH_ONLY_OPENED=true` 时，没领到宝箱不会推送；如果执行出错，仍会推送错误信息。

## 本地运行

PowerShell 示例：

```powershell
$env:REDMAGIC_ACCESS_TOKENS="your-token"
python .\redmagic_auto_sign.py
```

只跑宝箱：

```powershell
$env:REDMAGIC_ACCESS_TOKENS="your-token"
python .\redmagic_auto_sign.py --box-only
```

只验证配置、不执行接口任务：

```powershell
$env:REDMAGIC_ACCESS_TOKENS="your-token"
python .\redmagic_auto_sign.py --dry-run
```

## 注意

- 不要把 token 提交到仓库代码里，只放 GitHub Secrets。
- 脚本不接收手机号、密码、短信验证码、OAuth code 等登录信息。
- GitHub Actions 的 cron 使用 UTC。主签到配置 `10 0,8,16 * * *` 约等于北京时间 08:10、16:10、次日 00:10。
