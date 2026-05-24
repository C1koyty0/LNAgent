# LNAgent

**Light Novel Agent** — 通过向大模型提问或下达指示，生成完全自定义的轻小说。

## 简介

LNAgent 是一个面向轻小说创作的 AI Agent 项目。你可以用自然语言描述世界观、角色、情节走向与文风偏好，由大模型协助续写、扩写或从零生成章节内容。

当前版本提供基于 LangChain 的命令行对话入口，作为后续小说生成能力的基础框架。

**创作模式（规划）**：对话式续写——作者给出启发与大致走向，LLM 扩展丰富；关键操作（采纳正文、切换场景）由作者显式命令触发，Agent 可建议但不代为决策。

## 功能

| 状态 | 能力 |
|------|------|
| 已有 | **CLI 对话**：命令行单轮问答，验证模型连通性与提示效果 |
| 已有 | **OpenAI 兼容 API**：支持官方 OpenAI 及任意兼容接口（如本地部署、第三方网关） |
| 规划中 | **场景化短期记忆**：当前场景对话 + 前文衔接，场景切换时自动归档 |
| 规划中 | **Hot Canon / Cold Archive**：事实型设定即刻生效；叙事摘要作者确认后写入 |
| 规划中 | **Story Bible**：角色、能力、世界观、伏笔等结构化设定管理 |
| 规划中 | **正文采纳与导出**：按场景归档已采纳正文 |

设计细节见 [`docs/features/memory-architecture.md`](docs/features/memory-architecture.md)。

## 技术栈

| 项目 | 说明 |
|------|------|
| Python | >= 3.10，< 4.0（推荐 3.12） |
| [LangChain](https://python.langchain.com/) | 1.3.x，统一 LLM 调用 |
| [langchain-openai](https://python.langchain.com/docs/integrations/chat/openai/) | OpenAI 兼容 Chat 模型 |

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/LNAgent.git
cd LNAgent
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `API_KEY` | 是 | 大模型 API 密钥 |
| `MODEL` | 否 | 模型名称，默认 `gpt-4o-mini` |
| `API_BASE_URL` | 否 | 自定义 API 基址（兼容 OpenAI 格式的服务） |

```bash
# Windows (PowerShell)
$env:API_KEY = "your-api-key"
$env:MODEL = "gpt-4o-mini"

# macOS / Linux
export API_KEY="your-api-key"
export MODEL="gpt-4o-mini"
```

### 4. 运行

```bash
python main.py --project my_novel
```

启动后在终端输入创作指示；输入 `quit`、`exit` 或 `q` 退出。项目不存在时将引导创建并填写世界观 meta。

### CLI 命令（规划）

作者通过**显式命令**控制记忆写入；**记忆存储对用户无感知**（JSON 由系统管理，不直接编辑文件）。

| 命令 | 别名 | 说明 |
|------|------|------|
| `/adopt` | `/a` | 编辑并采纳上一轮输出；Hot Canon diff **y/n** 确认 |
| `/scene` | `/sc` | 结束场景（须至少一次 `/a`）；Cold 摘要全文 review |
| `/undo` | `/u` | 撤销最后一次 adopt；正文 + Hot **一并回滚** |
| `/fix` | `/f` | 设定纠错，仅改 Hot Canon（diff **y/n**） |
| `/canon` | `/c` | 查看 Hot Canon 摘要 |
| `/help` | `/h` | 命令帮助 |
| `/reject` | `/r` | Cold review 时丢弃提案 |
| `quit` / `exit` / `q` | — | 退出 |

Agent 以**启发式**建议切换场景，但**不会自动执行** `/sc`。

## 项目结构

```
LNAgent/
├── main.py              # CLI 入口
├── lnagent/
│   ├── config.py        # 环境变量配置
│   ├── llm.py           # 模型初始化
│   └── chat.py          # 对话客户端
├── docs/
│   └── features/        # 功能设计文档
│       └── memory-architecture.md
└── requirements.txt
```

## 作为库使用

```python
from lnagent import LLMChatClient, Settings, create_chat_model

settings = Settings.from_env()
client = LLMChatClient(create_chat_model(settings))
reply = client.chat("写一段异世界轻小说开篇，主角是转生到魔法学院的普通学生。")
print(reply)
```

## 路线图

- [ ] 多轮会话与场景化短期记忆（当前场景 + 前文衔接）
- [ ] Hot Canon（能力 / 状态即刻生效）与 Cold Archive（叙事摘要作者确认）
- [ ] Story Bible 与按场景正文归档（`/adopt`、`/scene` 命令）
- [ ] Cold Archive 确认流（场景摘要 edit / accept / reject）
- [ ] 可配置的文风与叙事模板
- [ ] 向量 RAG 检索（扩展预留，MVP 不做）

## 设计文档

- [记忆架构](docs/features/memory-architecture.md) — 设计共识与 CLI 约定
- [待讨论项](docs/features/open-questions.md) — 尚未拍板的问题 backlog
- [记忆 MVP 计划](docs/features/memory-mvp-plan.md) — 分阶段实现路线（Phase 0–4）

## 许可证

待定。
