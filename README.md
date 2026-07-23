# 飞球直播 Token 自动获取

全自动拿 `access_token`（易盾 protector，无需人工点验证码）。

**不依赖 Cloudflare D1**。定时任务用 **GitHub Actions** 或 **Render Cron** 跑浏览器环境即可。

## 原理

1. Playwright 打开站点，调用 `createNEGuardian().getToken()` 拿易盾 token  
2. `POST /v220/user/login/pass`，`captcha_validate` = 易盾 token  
3. 得到 `data.access_token` → 写入 `token.txt` / `token.json`

## 本地运行

```bash
pip install -r requirements.txt
playwright install chromium

# 方式 A：config.json
cp config.example.json config.json
# 编辑账号密码

python get_token.py

# 方式 B：环境变量
set FQZB_ACCOUNT=you@mail.com
set FQZB_PASSWORD=yourpass
python get_token.py
```

输出：

- `token.txt` 纯 JWT  
- `token.json` 完整信息  

## GitHub Actions（推荐）

1. 把本目录推到 GitHub 仓库  
2. Repo → Settings → Secrets → Actions 添加：
   - `FQZB_ACCOUNT`
   - `FQZB_PASSWORD`
3. 打开 Actions → **Refresh FQZB Token** → Run workflow  
4. 成功后在该 run 的 **Artifacts** 下载 `fqzb-token`（含 token.txt）

默认每 12 小时自动跑一次（可改 `.github/workflows/refresh-token.yml`）。

## Render Cron（可选）

1. 新建 Cron Job，连这个仓库  
2. Build: `pip install -r requirements.txt && playwright install --with-deps chromium`  
3. Command: `python get_token.py`  
4. Schedule: `0 */12 * * *`  
5. 环境变量：`FQZB_ACCOUNT` / `FQZB_PASSWORD`  

Render 上 token 在磁盘上会随实例回收丢失；若只想「定时刷一次、自己下载/转发」，可在脚本末尾加一行推送到你自己的 webhook。

## 使用 token

```http
GET https://openim-php-api.qaek4a2wjx6bt.cc/v220/user/my
authorization: <token.txt 内容>
device: 3
version: 1.9.7
api-version: 8
platform: fqzb
```

## 安全

- 不要把 `config.json` / `token.*` 提交进 git  
- 账号密码只用 Secrets / 环境变量  

## 直接写入仓库根目录

当前 GitHub Actions 会在登录成功后执行：

```bash
git add -f token.txt
git commit -m "chore: refresh fqzb token [skip ci]"
git push
```

也就是说，`token.txt` 会直接出现在仓库根目录。注意仓库必须是 private，否则 token 会泄露。
