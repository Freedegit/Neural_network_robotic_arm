# 机械臂动作客户端（左 / 右 / 停）

本仓库只保留 **客户端**。机械臂同学使用他们自己的 `servicer.py` 作为服务端；
之前的参考服务 `action_server.py` 已删除，不要在本仓库里再启动同名服务。

## 固定协议

TCP，UTF-8，一行一条命令，以 `\n` 结束：

| 动作 | 线上值 |
|---|---:|
| 左转 left | `-1` |
| 右转 right | `1` |
| 不转 stop | `0` |

服务端不回包。客户端发送后立即返回，不读取回复。

## 客户端用法

在 `arm_controller/` 目录下：

```powershell
# 单次发送
python action_client.py --action left  --host 172.30.187.22 --port 9000
python action_client.py --action right --host 172.30.187.22 --port 9000
python action_client.py --action stop  --host 172.30.187.22 --port 9000

# 连续输入：保持一个 TCP 连接，逐行发送，不等回包
python action_client.py --interactive --host 172.30.187.22 --port 9000
# 然后输入 left / right / stop / q
```

`--host` 默认 `172.30.187.22`（可用环境变量 `ARM_HOST` 覆盖）；`--port`
默认 `9000`（`ARM_PORT`）。

## 和 SNN 的映射

Fig.4 复现里的动作枚举是：

| SNN 动作 | 数值 | 线上值 |
|---|---:|---:|
| TURN_LEFT | 0 | `-1` |
| TURN_RIGHT | 1 | `1` |
| NO_DECISION | 2 | `0` |

## 重要限制

- **`sent` 只代表 TCP 写入成功**，不代表机械臂收到、执行或到位；没有 ack。
- 真机第一次测试必须由机械臂负责人现场确认，手边有急停；先小步、低速。
- `stop` 只是发送 `0`；对方 `servicer.py` 是否把 `0` 实现成“本次不动作”还是
  “中断当前运动”，由对方代码决定。急停请用示教器/急停按钮。
- 连续输入时不要连发多条；机械臂运动是串行的，等上一条动作完成后再发下一条。
- 对方 `servicer.py` 必须把 `-1` 映射成左转、`1` 映射成右转、`0` 映射成不转；
  旧的 `end_move` 只处理 `0/1`，需要他们改。
- 本仓库没有服务端，也没有把 SNN 决策循环直接接到 TCP；当前只提供客户端和映射。

## 自动接收模式

一次启动，持续接收上游 SNN/root 发来的动作，再转发给机械臂：

```powershell
# 本机监听 9000，上游连 127.0.0.1:9000；arm 服务端在 172.30.187.22:9000
python action_client.py --auto --from-snn --listen-port 9000 `
  --host 172.30.187.22 --port 9000

# 先不连真机，只看日志
python action_client.py --auto --from-snn --listen-port 9000 --dry-run
```

- `--from-snn`：输入 `0/1/2` -> 左/右/停；也接受 `left/right/stop`。
- `--listen-host` 默认 `0.0.0.0`；`--listen-port` 默认 `9000`。
- 如果 `action_client.py` 和 `servicer.py` 在同一台机器，两个 9000 会冲突；
  把 `--listen-port` 改成 `9100`，上游连 `9100`。
- 仍是无回包、fire-and-forget；`sent` 只代表 TCP 写入。
