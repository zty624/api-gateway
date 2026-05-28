# api-gateway

一个轻量级的 LLM API 跳板网关，面向内网服务提供统一出口。  
网关接收来自内网服务的请求，按配置转发到外部 LLM 或内部模型服务，默认支持 OpenAI 风格接口路径。

## 特性

- 配置驱动：所有路由与上游地址通过 YAML 文件定义。
- 内网鉴权：通过请求头 token 白名单控制访问。
- 路由分流：按路径前缀匹配选择不同上游。
- 流式透传：兼容 `stream=true` 的 SSE 转发。
- 轻量部署：纯 Python + FastAPI，`uv` 即可运行。

## 快速开始

1. 安装依赖（推荐 `uv`）：

```bash
uv sync
```

2. 复制配置示例并填入真实密钥环境变量：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
listen:
  host: 0.0.0.0
  port: 18080
auth:
  enabled: true
  header_name: X-INTERNAL-KEY
  tokens:
    - demo-token
upstreams:
  - path_prefix: /v1
    upstream_base: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    api_key_header: Authorization
    api_key_prefix: Bearer
    timeout_seconds: 60
```

3. 运行服务：

```bash
GATEWAY_CONFIG=config.yaml uv run python -m api_gateway
```

4. 访问示例（按你内网服务的 token 调用）：

```bash
curl -X POST http://127.0.0.1:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-INTERNAL-KEY: demo-token" \
  -d '{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"你好"}]}'
```

## 配置项说明

- `listen`: 网关监听地址与端口。
- `auth`: 鉴权开关、头名和 token 白名单（用于内网接入控制）。
- `upstreams`: 路由列表。
  - `path_prefix`: 请求路径前缀匹配（按长度从长到短匹配）。
  - `upstream_base`: 实际转发的上游基础 URL。网关会先移除 `path_prefix` 再拼接后续路径，所以这里可以是完整 `https://api.openai.com/v1` 或仅 `https://api.openai.com`。
  - `api_key_env`: 从环境变量读取上游密钥。
  - `api_key_header` / `api_key_prefix`: 组装上游鉴权头。

## 开发与验证

```bash
uv run ruff check src tests
uv run pytest
```

## 文件说明

- `src/api_gateway/`：网关核心代码。
- `config.example.yaml`：配置样例。
- `tests/`：最小化测试用例。
