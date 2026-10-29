# 在 Agent 里用一句话安装

先把安装包解压到固定位置，用 WorkBuddy、TRAE 或 Claude Code 打开解压后的 `shopdate-mcp` 文件夹。Agent 必须有本地终端与文件写入权限；Python 需为64位3.11+。源码仓库：https://github.com/vikk-hi/shopdate-MCP 。可git clone或下载ZIP；目录名称以实际下载/克隆结果为准。

直接把这一句话发给 Agent：

> 请按当前目录的 AGENT_INSTALL.md，为我安装 shopdate MCP 并接入当前客户端及当前项目，保留其他 MCP 配置并备份原文件，验证两个服务的连接和 commands 帮助调用；需我完成的登录、信任或插件步骤明确列出，不取业务数据。

这句话授权下面的安装及配置合并流程。它不是绕过客户端登录、权限或插件授权的命令；只有聊天能力、没有本地执行权限的Agent无法执行安装。Claude Desktop与Claude Code是不同产品，本教程的一句话自动流程针对Claude Code；Desktop使用README的生成配置，尚未实测。

## Agent 应执行的步骤

1. 确认当前文件夹包含 `installer.py`、`components/ali`、`components/jd`。用64位Python运行 `-B scripts/verify_release.py` 检查干净包；安装后生成的运行目录不属于干净包，不要为了让审计通过而删除用户数据。
2. Windows运行下面的PowerShell命令；macOS运行下面的sh命令。依赖下载或检查失败时不得报告成功。已有Python时不重装客户端或Python。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

```sh
sh ./install.sh
```

若官方PyPI超时，可在告知用户所用软件源后，Windows追加 `-IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple`；macOS追加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`。不关闭TLS验证，不修改全局pip配置。Windows可用 `-Python` 指定实际的64位Python。

3. 使用新环境执行配置合并。以下 `PROJECT_DIR` 必须替换为客户端实际打开的现有项目绝对路径，不按用户名猜测路径。Windows用 `.\.venv\Scripts\python.exe`；macOS用 `./.venv/bin/python`。

```powershell
.\.venv\Scripts\python.exe -B scripts/register_project.py --client workbuddy --project "PROJECT_DIR"
.\.venv\Scripts\python.exe -B scripts/register_project.py --client claude-code --project "PROJECT_DIR"
.\.venv\Scripts\python.exe -B scripts/register_project.py --client trae --project "PROJECT_DIR"
```

三行只执行当前客户端对应的一行。WorkBuddy与Claude Code写入项目 `.mcp.json`；TRAE写入 `.trae/mcp.json`，但必须先确认所用版本支持项目MCP，且项目MCP开关已开启。当前官方TRAE IDE文档支持该方式；本机旧版TraeWork CN 0.2.2未验证项目方式。

TRAE不支持项目配置时，由客户端设置界面确认实际JSON文件位置后使用：

```powershell
.\.venv\Scripts\python.exe -B scripts/register_project.py --client trae --config-file "ACTUAL_MCP_JSON"
```

不要猜测客户端用户目录。合并器同时识别 `mcpServers` 与TRAE原生 `servers`，保留 `inputs` 和其他服务。只补入两个shopdate服务；同名配置冲突、JSONC或不合法JSON会停止，交由用户在客户端界面处理，不覆盖现有服务。已有文件的逐字节备份写到安装目录 `.local/client-backups`，输出具体备份位置；配置相同再次执行不改写。客户端自身随后可能重排JSON格式，WorkBuddy实测如此。

WorkBuddy也可从安装器输出 `MCP_CONFIG_EXPORT` 批次中，分别导入 `workbuddy/shopdate-jd/mcp.json` 与 `workbuddy/shopdate-symc/mcp.json`，每个连接器一个服务。TRAE自定义MCP界面使用 `trae/mcp.json`，不要把通用配置直接写进原生 `servers` 文件。

4. 让用户按客户端提示信任项目MCP并刷新/重启MCP服务。Claude Code或WorkBuddy CLI已可用时，用客户端原生 `mcp get shopdate-jd` 和 `mcp get shopdate-symc` 检查Connected；WorkBuddy内置引擎未必暴露PATH命令，不应依赖开发者电脑上的私有启动路径。TRAE导入成功只证明配置登记，必须在设置界面另看运行状态。
5. 先做离线协议检查：用虚拟环境Python运行 `-B scripts/check_mcp.py`。再在已登录的Agent对话里明确调用两个服务的 `commands`：京东platform=jd，阿里分别platform=sycm、alimama。核对返回的工具结果，不能只看进程退出码；既有WorkBuddy认证失败测试仍返回0，Claude结果中 `is_error=true`。若Agent未登录或工具未获授权，明确记录未完成，不能用标准协议检查替代客户端真实调用。
6. 业务使用前，用户按README加载Chrome扩展并登录本人后台。安装验收不调用 `doctor`、`stores`、`account`、`run` 或工作流取数。以后取数只调用对应shopdate MCP，不使用Computer Use或其他补取通道；没有接口就列缺口。

## 当前实测与限制

| 客户端 | 已验证 | 仍缺少 |
|---|---|---|
| WorkBuddy 5.8.3 | 已安装客户端内置CLI；两服务登记及Connected；项目合并后仍Connected | 独立测试profile未登录，Agent调用提示Authentication required；桌面设置界面与登录后的对话调用未验证 |
| TRAE / TraeWork CN 0.2.2 | 原生CLI隔离profile导入；原生servers结构；无空格command启动器的标准MCP握手和commands | 桌面前端实际加载、聊天工具调用；旧版项目配置支持 |
| Claude Code 2.1.312 | 临时安装官方Windows x64原生CLI；隔离配置登记；两服务Connected | Agent调用返回Not logged in；登录后的模型调用 |
| Claude Desktop | 提供配置 | 未安装，未验证 |
| macOS | 提供脚本与配置 | 没有Mac实机，Intel和Apple Silicon均未验证 |

TRAE官方要求command不含空格。安装器在需要时生成无空格的系统Python命令，通过 `scripts/launch_venv_mcp.py` 启动本包虚拟环境；路径中的空格保留在args内。Windows降级为 `py -3-64` 时需Python Launcher，macOS降级为 `python3` 时需可在客户端PATH找到；缺失则安装正确Python或换无空格路径后重新导出，不手工删除引号或拆分args。

官方参考：[WorkBuddy连接器](https://open.workbuddy.cn/docs/connector)、[CodeBuddy CLI MCP](https://www.codebuddy.cn/docs/cli/mcp)、[TRAE IDE MCP](https://docs.trae.cn/ide_add-mcp-servers)、[Claude Code MCP](https://code.claude.com/docs/en/mcp)。
