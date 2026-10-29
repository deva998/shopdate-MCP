# 兼容性与验证范围

公开测试版：2026.10.29-r5。安装/协议通过不等于所有业务模块、账号和日期都已完成取数验收。

| 系统或客户端 | 已验证 | 尚未验证或存在限制 |
|---|---|---|
| Windows x64 / Python 3.11.9 | 中文空格路径、清华HTTPS镜像全新依赖安装、两侧服务加载及标准MCP协议 | 官网文件CDN曾超时，不能承诺所有网络均可安装 |
| WorkBuddy 5.8.3 | 已安装应用内置CLI登记，两服务Connected | 独立测试profile未登录，Agent对话调用未完成；桌面UI调用未验证 |
| Claude Code 2.1.312 | 临时官方Windows原生CLI登记，两服务Connected | 未完成普通PATH安装验收；未登录，Agent对话调用未完成 |
| TraeWork CN 0.2.2 | 原生CLI隔离配置导入；TRAE启动配置标准MCP协议通过 | 桌面前端调用、旧版项目配置支持未验证 |
| Claude Desktop / Cursor | 提供配置模板 | 未完成实机验收 |
| 豆包工作 | 提供条件模板 | 所用版本需支持本地stdio，未完成实机验收 |
| Intel / Apple Silicon Mac | 提供安装脚本和POSIX配置 | 未完成Mac实机依赖、插件和业务验收 |

本版回归覆盖配置生成、在线/离线参数、TRAE路径、JSON合并与备份等18项；MCP协议检查只执行initialize、tools/list、commands、guide和workflow_catalog，不执行业务取数。首次发布沿用此前Windows安装与客户端连接证据，未将历史结果改写成全部本轮实测。

r5修复了从Git克隆后根目录.git导致文件审计失败的问题；根Git元数据不列入哈希或ZIP，嵌套仓库和运行目录仍被拒绝。源码未携带真实账号、业务响应或已安装虚拟环境。

天猫行业/市场排名未接入；其余模块也需本人账号授权并核对实际返回质量，详见[功能与缺口](FEATURES.md)。不能把帮助调用、健康检查或Connected写成完整业务取数成功。
