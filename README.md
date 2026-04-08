# xboard-node-tools

在节点服务器本机采集 `x-ui / 3x-ui` 入站，或手工创建节点 JSON，再在 Xboard 服务器侧统一预览并导入。

当前默认策略：

- 检测到 `x-ui / 3x-ui` 时：
  - 保留原节点名称
  - 不复用原端口
  - 自动生成一条同名、不同端口的新节点 JSON
  - 这类结果只作为迁移草稿，不自动上传到 Xboard
- 没有 `x-ui / 3x-ui` 时：
  - 只问你协议和名称
  - 其余端口、UUID、密码、Reality 参数全部自动生成

这套工具专门为“不走集中 SSH、逐台登录服务器处理”的运维方式准备。

现在已经提供统一的一键入口，不需要你自己分别记 `node_probe.py` 和 `xboard_import.py` 的执行步骤。

## 一键安装

### 稳定版

```bash
curl -fsSL https://github.com/JackLuo1980/xboard-node-tools/raw/main/install.sh | bash
```

### 预置默认 Xboard 并安装后自动运行

安装脚本支持通过环境变量预置默认 Xboard 配置。这样安装完成后，`上传到 Xboard` 会直接复用这些值，不再反复询问。

```bash
XBOARD_DEFAULT_SSH_HOST="your-xboard-host" \
XBOARD_DEFAULT_SSH_USER="root" \
XBOARD_DEFAULT_SSH_PASSWORD="your-ssh-password" \
XBOARD_DEFAULT_REMOTE_JSON_DIR="/root" \
XBOARD_DEFAULT_DB_HOST="127.0.0.1" \
XBOARD_DEFAULT_DB_PORT="3306" \
XBOARD_DEFAULT_DB_NAME="xboard" \
XBOARD_DEFAULT_DB_USER="xboard" \
XBOARD_DEFAULT_DB_PASSWORD="your-db-password" \
XBOARD_DEFAULT_GROUPS="vip1,vip2,vip3" \
AUTO_RUN="true" \
AUTO_MODE="menu" \
curl -fsSL https://github.com/JackLuo1980/xboard-node-tools/raw/main/install.sh | bash
```

如果你想安装后直接进入上传流程，可以把 `AUTO_MODE` 改成：

```bash
AUTO_MODE="upload"
```

如果你是自己批量给很多机器同步，推荐直接改成：

```bash
AUTO_MODE="sync"
```

`sync` 会自动做两步：

1. 非交互导出现有节点到 `主机名.nodes.json`
2. 立刻上传到你预置好的默认 Xboard

安装完成后，直接运行：

```bash
xboard-nodes
```

### 直接进入采集模式

```bash
xboard-nodes --mode export
```

### 直接进入上传模式

```bash
xboard-nodes --mode upload
```

### 直接进入创建新节点模式

```bash
xboard-nodes --mode create
```

### 直接一键同步

```bash
xboard-nodes --mode sync
```

### 已安装后的升级

```bash
curl -fsSL https://github.com/JackLuo1980/xboard-node-tools/raw/main/install.sh | bash
```

当前安装脚本是覆盖式安装，重复执行即可升级到最新版本。

## 功能

- 自动检测本机 `x-ui / 3x-ui`
- 逐条确认是否按“同名平行新节点”导出已有入站
- 没有面板时只需选择协议和名称
- 导出统一 JSON
- 对于非 `x-ui` 的正式节点，在 Xboard 服务器做 `dry-run`
- 确认后写入 `v2_server`
- 默认加入 `vip1 / vip2 / vip3`

## 文件

- `node_probe.py`
  - 节点服务器本机运行
  - 负责采集和生成 JSON

- `xboard_import.py`
  - Xboard 服务器本机运行
  - 负责预览和导入节点
  - 支持 `--result-output` 写出带 NodeID 的结果 JSON

- `xrayr_config.py`
  - 根据导入结果 JSON 生成 XrayR 配置模板
  - 用于把新节点继续接成真正在线状态

- `xboard_nodes.py`
  - 统一一键入口
  - 菜单式选择“导出 / 上传 / 创建新的”
  - `创建新的` 会先检测本机是否有 `x-ui / 3x-ui`，有的话优先创建同类平行节点
  - `x-ui` 结果只保留为迁移草稿，不再自动上传到 Xboard

- `run.sh`
  - Shell 快捷入口
  - 等价于执行 `python3 xboard_nodes.py`

- `install.sh`
  - 安装脚本
  - 会把仓库安装到 `/opt/xboard-node-tools`
  - 并创建全局命令 `xboard-nodes`

- `examples/sample.nodes.json`
  - 导出格式示例

## 一键用法

### 推荐方式

```bash
python3 xboard_nodes.py
```

或者：

```bash
bash run.sh
```

运行后会出现菜单：

```text
1. 导出现有节点到 JSON
2. 上传到 Xboard
3. 创建新的节点 JSON
4. 一键同步到 Xboard
5. 退出
```

如果你已经执行过一键安装，推荐直接用：

```bash
xboard-nodes
```

现在的默认交互是：

- 导出完成后，会直接询问是否继续上传到 Xboard
- 导出完成后，如果结果来自 `x-ui / 3x-ui`，会直接停在草稿阶段，不再进入上传
- 上传时会自动优先发现当前目录最新的 `*.nodes.json`
- 第一次上传会提示填写 Xboard SSH 和数据库信息
- 如果安装时已经预置默认 Xboard 配置，这些信息会直接复用
- 否则第一次填写后也可以保存为默认值，后面尽量少重复输入
- 创建新的节点会直接跳过 `x-ui / 3x-ui` 检测，只要求输入协议和名称
- 创建新的节点会先检测 `x-ui / 3x-ui`，有面板时优先复制现有入站为同类平行节点
- 一键同步会直接“非交互导出 + 上传到默认 Xboard”

### 节点服务器上

选择 `1`：

- 自动检测 `x-ui / 3x-ui`
- 逐条确认是否使用同名平行新节点
- 最后生成 `*.nodes.json`
- 如果是 `x-ui / 3x-ui` 草稿，不会继续上传到 Xboard

选择 `3`：

- 先检测 `x-ui / 3x-ui`
- 有面板时优先复制现有入站为同类平行节点
- 没有面板时才进入手工建节点模式

选择 `4`：

- 适合你这种批量同步很多机器的场景
- 不再逐条询问导出
- 直接自动导出并上传到默认 Xboard

### 上传到 Xboard

选择 `2`：

- 自动找到当前目录最新的 `*.nodes.json`
- 使用 `ssh/scp` 上传到你的 Xboard 服务器
- 远端自动安装或更新 `xboard-node-tools`
- 远端先执行 `dry-run`
- 你确认后，再执行 `--apply`

## 旧方式

如果你想继续单独调用底层脚本，也保留支持。

### 1. 在节点服务器本机采集

```bash
python3 node_probe.py -o hk-01.nodes.json
```

如果检测到 `x-ui / 3x-ui`，脚本会逐条询问是否导出。  
如果没有检测到，就进入手工建节点模式。

### 2. 把 JSON 放到 Xboard 服务器

例如：

```bash
hk-01.nodes.json
```

### 3. 在 Xboard 服务器先做预览

```bash
python3 xboard_import.py hk-01.nodes.json \
  --db-user xboard \
  --db-password 'your-password'
```

默认只打印导入计划和 SQL，不会直接写库。

### 4. 确认后正式导入

```bash
python3 xboard_import.py hk-01.nodes.json \
  --db-user xboard \
  --db-password 'your-password' \
  --apply
```

如果你想拿到后续的 XrayR 配置模板，推荐正式导入时同时写结果文件：

```bash
python3 xboard_import.py hk-01.nodes.json \
  --db-user xboard \
  --db-password 'your-password' \
  --apply \
  --result-output hk-01.import-result.json
```

然后根据结果文件生成 XrayR 配置模板：

```bash
python3 xrayr_config.py hk-01.import-result.json \
  --panel-host https://x.asli.eu.org \
  --api-key 'your-panel-key' \
  --output ./xrayr-configs
```

## 典型场景

### 已有 3x-ui / x-ui

1. 登录服务器
2. 运行 `xboard-nodes`
3. 选 `1`
4. 逐条确认已有入站
5. 导出 JSON
6. 直接继续上传到 Xboard

### 全新空机

1. 登录服务器
2. 运行 `xboard-nodes`
3. 选 `3`
4. 进入手工创建节点
5. 只输入协议和名称
6. 导出 JSON
7. 直接继续上传到 Xboard

## 参数说明

### `node_probe.py`

```bash
python3 node_probe.py --help
```

主要参数：

- `-o, --output`
  - 输出 JSON 路径

- `--host`
  - 手工指定导出的主机地址

- `--non-interactive`
  - 非交互模式
  - 有面板时自动导出全部入站
  - 没有面板时直接退出

- `--manual-only`
  - 跳过 `x-ui / 3x-ui` 检测
  - 直接进入手工创建模式

### `xboard_import.py`

```bash
python3 xboard_import.py --help
```

主要参数：

- `--db-host`
- `--db-port`
- `--db-name`
- `--db-user`
- `--db-password`
- `--groups`
  - 默认 `vip1,vip2,vip3`

- `--apply`
  - 真正写入数据库

- `--force-insert`
  - 不做查重，直接插入

### `xboard_nodes.py`

```bash
python3 xboard_nodes.py --help
```

主要参数：

- `--mode menu`
  - 默认菜单模式

- `--mode export`
  - 直接进入导出现有节点流程

- `--mode upload`
  - 直接进入上传到 Xboard 流程

- `--mode create`
  - 直接进入手工创建新节点流程

- `--mode sync`
  - 直接非交互导出并上传到默认 Xboard

## 默认行为

- 上传目标默认是你保存过的 Xboard 配置
- 远端导入目标表：`v2_server`
- 默认按 `type + host + server_port` 查重
- 默认把权限组写成 JSON 字符串数组
- 默认 `show = 1`
- 默认 `rate = 1`
- 默认 `status = 1`

## 已知前提

1. `xboard_import.py` 依赖目标机器有 `mysql` 命令
2. 当前默认面向 Xboard 的统一 `v2_server` 表结构
3. `vless reality` 的密钥生成依赖本机存在 `xray / XrayR` 的 `x25519` 命令
4. 如果本机没有相关命令，Reality 密钥字段会留空，后续需要手工补

## 后续可扩展

- 目录级批量导入多个 JSON
- 直接生成 XrayR 配置
- NAT 端口批量规划
- 自动检测和修正重复节点
- 支持更多 3x-ui 数据路径

## License

MIT
