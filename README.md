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
- 宝箱领取：`points/home/openbox` 后使用响应的 `energyId` 调用 `points/home/havingenergy` 确认到账
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
  .github/workflows/release.yml
```

## 下载发行版

在仓库的 [Releases](https://github.com/COMICFLY/redmagic-bbs-auto-sign/releases) 页面下载对应文件，运行时不需要另外安装 Python：

| 文件 | 适用环境 |
| --- | --- |
| `redmagic-auto-sign-windows-x64.zip` | 64 位 Windows，解压后运行 `.exe` |
| `redmagic-auto-sign-linux-x64.tar.gz` | 64 位 GNU/Linux（glibc），解压后运行 `redmagic-auto-sign` |

每个压缩包都附带 `.sha256` 校验文件。Linux 如果丢失执行权限，先运行 `chmod +x redmagic-auto-sign`。ARM、Alpine Linux 等环境请直接使用 Python 脚本。

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

这个模式会先查 `nextOpenTime` / `boxWaitingOpen`，只有可领取时才调用 `points/home/openbox`，再使用响应中的 `energyId` 调用 `points/home/havingenergy` 确认领取。`REDMAGIC_BOX_PUSH_ONLY_OPENED=true` 时，没有成功确认领取不会推送；如果开箱或确认领取出错，仍会推送错误信息。

## 本地运行

程序只读取当前系统或终端会话中的环境变量，不会自动加载 `.env` 文件。以下示例使用单账号变量 `REDMAGIC_ACCESS_TOKEN`；多账号时请改用前文的 `REDMAGIC_ACCESS_TOKENS`。

### Windows 可执行文件

从 [Releases](https://github.com/COMICFLY/redmagic-bbs-auto-sign/releases) 下载并解压 `redmagic-auto-sign-windows-x64.zip`，然后在解压目录打开 PowerShell：

```powershell
$env:REDMAGIC_ACCESS_TOKEN="your-token"
.\redmagic-auto-sign.exe
```

发行包未进行代码签名。如 Windows 提示未知发布者，请先使用发行页提供的 `.sha256` 文件核对下载内容，再决定是否运行。

### Linux 可执行文件

下载 `redmagic-auto-sign-linux-x64.tar.gz` 及其 `.sha256` 文件后执行：

```bash
sha256sum -c redmagic-auto-sign-linux-x64.tar.gz.sha256
tar -xzf redmagic-auto-sign-linux-x64.tar.gz
chmod +x redmagic-auto-sign
export REDMAGIC_ACCESS_TOKEN="your-token"
./redmagic-auto-sign
```

该发行包适用于 x64 glibc Linux。ARM、Alpine Linux 等环境请使用源码运行。

### Python 源码

建议使用 Python 3.12。项目运行时仅使用 Python 标准库，无需安装额外依赖。

Windows PowerShell：

```powershell
$env:REDMAGIC_ACCESS_TOKEN="your-token"
python .\redmagic_auto_sign.py
```

Linux：

```bash
export REDMAGIC_ACCESS_TOKEN="your-token"
python3 redmagic_auto_sign.py
```

### 常用参数

可执行文件和 Python 源码支持相同参数：

| 参数 | 作用 |
| --- | --- |
| `--box-only` | 仅检查并领取宝箱 |
| `--dry-run` | 仅检查配置，不发起签到、宝箱或转盘请求 |
| `--no-push` | 本次运行不发送推送 |

例如，在 Windows 中仅检查宝箱：

```powershell
$env:REDMAGIC_ACCESS_TOKEN="your-token"
.\redmagic-auto-sign.exe --box-only
```

## 注意

- 不要把 token 提交到仓库代码里，只放 GitHub Secrets。
- 脚本不接收手机号、密码、短信验证码、OAuth code 等登录信息。
- GitHub Actions 的 cron 使用 UTC。主签到配置 `0 0 * * *`，对应北京时间每天 08:00，签到和转盘会在同一次任务中完成；Actions 可能因调度延迟几分钟。
