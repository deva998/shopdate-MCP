# 在 Agent 中用一句话安装

需要64位 Python 3.11+、Chrome 116+，以及具有本地终端和文件写入权限的 Agent。

## 1. 发送安装指令

> 请从 https://github.com/deva998/shopdate-MCP.git 克隆项目，按 AGENT_INSTALL.md 安装并接入当前客户端，保留其他 MCP 配置；检查两个服务能否启动和调用，提示我完成插件加载、后台登录及客户端授权，最后说明是否安装成功，有问题时给出具体错误。

如果已经打开本项目目录，直接使用该目录，不重复克隆。没有本地执行权限时，按[首页手动安装](README.md#方式二手动安装)操作。

## 2. 完成必要的人工步骤

按 Agent 提示加载 Chrome 数据桥、登录本人后台，并在客户端确认 MCP 信任授权。验证码和安全验证由用户完成，不提供 Cookie、密码或 Token。

## 3. 检查是否可用

Agent 应确认两个服务都能返回 commands 帮助，再通过对应 MCP 的 doctor 检查需要使用的平台数据桥和后台登录。最终简要说明“成功”或“失败在哪一步、下一步怎么处理”。不查询经营报表，不把本地协议通过写成全部业务取数成功。

安装和故障排查见[首页](README.md)，系统及客户端限制见[兼容性说明](docs/VALIDATION.md)。

<details>
<summary>供执行安装的 Agent 使用：配置与检查命令</summary>

1. 先确认当前目录包含 installer.py 和 components，使用64位Python检查 `scripts/verify_release.py`；不要删除用户数据来迎合检查。
2. Windows运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`；Mac运行 `sh ./install.sh`。失败时先处理实际错误，禁止关闭TLS验证。
3. 使用安装器输出的MCP_CONFIG_EXPORT。只合并shopdate两个服务，不整份覆盖客户端配置。WorkBuddy、Claude Code可用以下项目合并脚本；TRAE先确认该版本支持且已开启项目MCP。

```powershell
.\.venv\Scripts\python.exe -B scripts/register_project.py --client workbuddy --project "PROJECT_DIR"
.\.venv\Scripts\python.exe -B scripts/register_project.py --client claude-code --project "PROJECT_DIR"
.\.venv\Scripts\python.exe -B scripts/register_project.py --client trae --project "PROJECT_DIR"
```

只执行当前客户端对应的一行。PROJECT_DIR是实际打开的现有项目绝对路径；Mac将Python启动路径换为 `./.venv/bin/python`。TRAE不支持项目方式时，先确认客户端实际JSON路径，再用 `--config-file "ACTUAL_MCP_JSON"` 替代 `--project`；不能猜测目录。

合并器备份原文件到 `.local/client-backups`，保留其他服务。同名冲突或JSONC会停止，不强行覆盖。WorkBuddy也可分别导入两个专用配置。Codex、Claude Desktop、Cursor使用输出目录中的对应文件进行合并。

4. 用虚拟环境Python执行 `-B scripts/check_mcp.py`，确认本地协议通过。随后在当前Agent实际调用shopdate-jd的commands（platform=jd），以及shopdate-symc的commands（platform=sycm、alimama）。没有实际工具结果时不能只凭退出码或Connected判成功。
5. 用户加载CHROME_EXTENSION目录的插件、完成后台登录和客户端授权后，仅通过对应MCP的doctor检查连接。仅针对用户准备使用的平台核对，不强求登录所有平台。仍有缺口时列出具体失败步骤。

所有取数均通过对应shopdate MCP，不使用Computer Use或其他补取通道；接口没有实现则明确列缺口。TRAE路径含空格时使用安装器生成的专用配置，保留args数组。Mac实机、部分客户端真实对话调用仍未完成全面验收。

</details>
