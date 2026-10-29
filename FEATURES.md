# 功能范围与明确缺口

发行版本：2026.10.29-r5（公开测试版）。本清单根据随包源码与既有验收记录整理，不代表当前账号每个模块都已取到完整数据。

## MCP服务

| 服务 | 平台参数 | 协议工具 |
|---|---|---|
| shopdate-jd | jd | doctor、commands、run、stores、account、modules、guide、workflow_catalog、workflow |
| shopdate-symc | sycm / alimama | doctor、commands、run、account、modules、guide、workflow_catalog、workflow |

commands列出命令与参数；workflow_catalog列出实现状态；做整份分析报告前先看guide。业务使用需另核对账号、日期、指标、分页与返回质量。安装验收仅调用帮助、指南和目录，不执行doctor、account、stores或run。

## 业务模块边界

| 模块 | 随包实现入口 | 本发行验收边界 |
|---|---|---|
| 京东商品、库存、交易退款 | 京东业务源码及命令目录 | 已包含实现；没有重新验证所有日期和模块的数据完整性；库存按当前SKU语义处理 |
| 京东行业 | 行业选项、大盘、商品榜、店铺榜查询入口 | 保留官方区间与返回排名范围，不承诺全市场覆盖 |
| 京东广告、客服 | 以workflow_catalog为准 | 目录中仍标为延后或未接入的项目不能当作已实现 |
| 生意参谋本店商品、交易退款等 | sycm原生命令与分析指南 | 已包含实现；需要本人账号权限和实际查询验收 |
| 万相台计划、活动、广告报表等 | alimama原生命令与广告复盘实现 | 已包含实现；历史报表的日期、归因窗口、分页口径需一致 |
| 天猫行业/市场排名 | 仅有离线接口候选契约 | workflow_catalog标记not_integrated，既有验证记录为blocked_by_browser_site_policy；未接入，不用本店类目销售替代行业排名 |
| 其他平台、自动预算调整及推广写操作 | 不纳入本包 | 不提供相应功能；上游自动模块下载清单已置空 |

安全策略阻断的历史记录不能推断为目前所有MCP接口都被阻断。没有现成实现或无法取得数据的需求须明确列缺口，不能通过Computer Use、其他浏览器自动化或直接HTTP请求补取。

## 客户端与系统缺口

- WorkBuddy 5.8.3：内置CLI两服务Connected；独立测试profile未登录，Agent对话调用未完成。
- Claude Code 2.1.312：临时官方原生CLI登记与Connected通过；登录后的Agent调用未完成。Claude Desktop未安装、未验证。
- TraeWork CN 0.2.2：原生CLI隔离配置导入通过；带空格安装路径的启动器标准MCP帮助调用通过；桌面前端调用、旧版项目MCP支持未验证。
- Mac Intel / Apple Silicon：提供脚本及配置，尚无实机安装与插件验收。
- Cursor、豆包工作：配置模板不等于客户端实测；豆包版本需确有本地stdio入口。
- 官网PyPI文件CDN下载曾超时；Windows清华HTTPS镜像冷安装通过，不能宣称所有网络都可用。

详情：[验证报告](VALIDATION.md)、[安装教程](AGENT_INSTALL.md)。
