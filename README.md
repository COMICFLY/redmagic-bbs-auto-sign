# RedMagic Auto Sign

红魔社区自动签到脚本，使用社区 H5 接口完成签到、转盘和宝箱领取。脚本只读取配置好的社区 `accessToken`，不处理账号密码或短信验证码。

## 免责声明

> [!WARNING]
> 本项目为非官方项目，仅供学习、研究及个人自动化使用，与红魔、努比亚及其关联方不存在授权、合作或从属关系。使用本项目即表示你已阅读、理解并同意以下内容。

- 仅可操作本人拥有或已获得明确授权的账号，并遵守所在地法律法规、红魔社区用户协议、活动规则及相关平台政策。
- 禁止用于批量账号操作、商业牟利、接口攻击、流量滥用、绕过安全或风控限制，以及任何侵犯他人权益或违反平台规则的行为。
- 社区接口、活动规则、奖励机制和账号策略可能随时变更。本项目不保证功能持续可用，也不保证运行结果完整、准确或符合预期。
- 自动化操作可能引发账号限制、活动资格取消、积分或魔力异常、奖励损失、接口限流等风险。使用者应自行评估并承担全部后果。
- `accessToken`、推送密钥及其他凭证均由使用者自行保管。因配置错误、凭证泄露、第三方服务故障或 GitHub Actions 使用产生的损失与费用，由使用者自行承担。
- 在适用法律允许的最大范围内，项目作者及贡献者不对使用、修改或分发本项目造成的任何直接或间接损失承担责任，也不提供任何明示或暗示的保证。
- 如你不同意以上内容，或无法确认使用行为是否合规，请立即停止使用并删除相关配置。

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

仓库包含独立宝箱工作流 `.github/workflows/redmagic-box.yml`，每 30 分钟检查一次：

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
- GitHub Actions 的 cron 使用 UTC。主签到配置 `0 16 * * *`，对应北京时间每天 00:00，签到和转盘会在同一次任务中完成。
