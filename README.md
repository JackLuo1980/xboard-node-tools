# xboard-node-tools

在节点服务器本机采集 `x-ui / 3x-ui` 入站，或手工创建节点 JSON，再在 Xboard 服务器侧统一预览并导入。

这套工具专门为“不走集中 SSH、逐台登录服务器处理”的运维方式准备。

现在已经提供统一的一键入口，不需要你自己分别记 `node_probe.py` 和 `xboard_import.py` 的执行步骤。

## 一键安装

### 稳定版

```bash
curl -fsSL https://raw.githubusercontent.com/JackLuo1980/xboard-node-tools/main/install.sh | bash
```

安装完成后，直接运行：

```bash
xboard-nodes
```

### 直接进入采集模式

```bash
xboard-nodes --mode probe
```

### 直接进入导入模式

```bash
xboard-nodes --mode import
```

## 功能

- 自动检测本机 `x-ui / 3x-ui`
- 逐条确认是否导出已有入站
- 没有面板时进入手工建节点向导
- 导出统一 JSON
- 在 Xboard 服务器做 `dry-run`
- 确认后写入 `v2_server`
- 默认加入 `vip1 / vip2 / vip3`

## 文件

- `node_probe.py`
  - 节点服务器本机运行
  - 负责采集和生成 JSON

- `xboard_import.py`
  - Xboard 服务器本机运行
  - 负责预览和导入节点

- `xboard_nodes.py`
  - 统一一键入口
  - 菜单式选择“采集”或“导入”

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
1. 采集本机节点并导出 JSON
2. 导入 JSON 到 Xboard
3. 退出
```

如果你已经执行过一键安装，推荐直接用：

```bash
xboard-nodes
```

### 节点服务器上

选择 `1`：

- 自动检测 `x-ui / 3x-ui`
- 逐条确认是否导出
- 没有面板时进入手工建节点模式
- 最后生成 `*.nodes.json`

### Xboard 服务器上

选择 `2`：

- 先让你填写数据库连接信息
- 先自动执行 `dry-run`
- 展示导入计划和 SQL
- 你确认后，再自动执行 `--apply`

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

## 典型场景

### 已有 3x-ui / x-ui

1. 登录服务器
2. 运行 `python3 xboard_nodes.py`
3. 选 `1`
4. 逐条确认已有入站
5. 导出 JSON
6. 到 Xboard 服务器再运行 `python3 xboard_nodes.py`
7. 选 `2`

### 全新空机

1. 登录服务器
2. 运行 `python3 xboard_nodes.py`
3. 选 `1`
4. 进入手工创建节点
5. 选择协议、端口、NAT 外部端口
6. 导出 JSON
7. 到 Xboard 服务器运行 `python3 xboard_nodes.py`
8. 选 `2`

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

- `--mode probe`
  - 直接进入采集流程

- `--mode import`
  - 直接进入导入流程

## 默认行为

- 导入目标表：`v2_server`
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
