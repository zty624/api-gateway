# 第一阶段实现总结

- 完成最小仓库结构（`src/`, `tests/`, `docs/`, 配置与文档文件）。
- 完成 YAML 配置模型与加载：
  - `listen`
  - `auth`
  - `upstreams`
- 实现网关核心：
  - 路径前缀匹配路由；
  - 内网 token 鉴权；
  - 普通请求转发；
  - `stream=true` 时 SSE 流式转发；
  - 上游鉴权头自动注入（来自环境变量）。
- 提供启动入口：
  - `python -m api_gateway`
  - `uv run gateway`（脚本入口）
- 提供最小测试：
  - 配置加载；
  - 路由匹配；
  - 缺少鉴权 token 的拒绝行为。
