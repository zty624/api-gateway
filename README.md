# api-gateway

一个面向集群容器的单端口远程 CLI 网关。容器内部运行 `sshd`、`rtunnel`
server、FastAPI 控制面和 nginx；外部只需要访问一个公开 URL：

- `/api/*`：登录、状态查询、tmux session 控制面。
- `/tunnel/`：给 `rtunnel` 客户端使用的 WebSocket TCP 隧道。

终端交互不由 HTTP 模拟。用户端通过 `rtunnel` 建本地 TCP 隧道，再用普通
`ssh` 进入容器并 attach 到 tmux，所以颜色、进度条、交互输入和 tmux 反馈都走
SSH/PTTY 原生流。

## 快速开始

1. 复制配置：

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

2. 编辑 `config.yaml`：

- `public_base_url` 改成集群给这个容器端口映射出来的 URL，例如
  `https://.../proxy/8080`。
- `auth.users` 改成实际用户和密码哈希。
- `tmux.default_cwd` 改成容器内默认工作目录。

生成密码哈希：

```bash
uv run python -c "from api_gateway.auth import hash_password; print(hash_password('your-password'))"
```

3. 准备 SSH 公钥：

```bash
cp ~/.ssh/id_ed25519.pub authorized_keys
```

4. 启动：

```bash
docker compose up -d --build
```

5. 登录拿 token：

```bash
curl -sS -X POST http://127.0.0.1:8080/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"demo-password"}'
```

6. 创建 tmux session 并获取连接命令：

```bash
TOKEN="<access_token>"

curl -sS -X POST http://127.0.0.1:8080/api/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"work","cwd":"/workspace"}'

curl -sS http://127.0.0.1:8080/api/sessions/work/connect \
  -H "Authorization: Bearer $TOKEN"
```

返回值会包含两条命令：

```bash
rtunnel https://example.com/proxy/8080/tunnel/ 127.0.0.1:2226 \
  -H 'Authorization: Bearer <token>'

ssh -p 2226 root@localhost -t 'tmux new-session -A -s gateway-work'
```

先启动 `rtunnel`，再执行 `ssh`，就能看到远端 tmux 的实时反馈。

## API

- `POST /api/login`
- `POST /api/logout`
- `GET /api/healthz`
- `GET /api/status`
- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{name}`
- `DELETE /api/sessions/{name}`
- `GET /api/sessions/{name}/connect`

除 `/api/login` 和 `/api/healthz` 外，API 都需要：

```text
Authorization: Bearer <token>
```

`/tunnel/` 同样需要这个 header，nginx 会先调用 FastAPI 的内部鉴权端点再把
WebSocket 连接转发给内部 rtunnel server。

## 开发验证

```bash
uv run ruff check src tests
uv run pytest
```

## 文件说明

- `src/api_gateway/app.py`：FastAPI 控制面。
- `src/api_gateway/auth.py`：PBKDF2 密码校验和内存 token。
- `src/api_gateway/tmux.py`：tmux session 管理。
- `deploy/nginx.conf.template`：单端口 `/api/` 与 `/tunnel/` 分流。
- `scripts/entrypoint.sh`：容器内启动 sshd、rtunnel、API 和 nginx。
