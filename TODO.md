# 任务拆解（可执行）

1. 建立基础文件：
   - [x] .gitignore
   - [x] pyproject.toml（uv 友好）
   - [x] 文档框架（README、配置示例）
2. 配置层：
   - [x] 定义 `GatewayConfig` 与 `RouteConfig`
   - [x] YAML 配置加载与校验
3. 网关实现：
   - [x] 创建鉴权依赖
   - [x] 创建路由匹配器（按前缀）
   - [x] 基于 `httpx` 的普通响应转发
   - [x] 基于 `httpx` 的 SSE 流转发
4. 启动与部署：
   - [x] CLI 启动入口
   - [ ] Docker + docker-compose 示例
5. 验证：
   - [x] 配置解析测试
   - [x] 内网鉴权 + 前缀路由测试
   - [ ] 至少一条手工转发验证清单
