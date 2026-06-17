# LNAgent

**Light Novel Agent** — 通过向大模型提问或下达指示，生成完全自定义的轻小说。

## 简介

LNAgent 是一个面向轻小说创作的 AI Agent 项目。你可以用自然语言描述世界观、角色、情节走向与文风偏好，由大模型协助续写、扩写或从零生成章节内容。

当前版本提供基于 LangChain 的命令行多轮创作入口，支持项目化记忆、正文采纳与场景切换；并提供第一版最小 Web/API 入口用于项目浏览、基础会话与显式采纳/切场景流程。

**创作模式（规划）**：对话式续写——作者给出启发与大致走向，LLM 扩展丰富；关键操作（采纳正文、切换场景）由作者显式命令触发，Agent 可建议但不代为决策。

## 功能

| 状态 | 能力 |
|------|------|
| 已有 | **多轮创作会话**：`--project` 项目模式，场景内对话 + 已 adopt 正文持久化 |
| 已有 | **OpenAI 兼容 API**：支持官方 OpenAI 及任意兼容接口（如本地部署、第三方网关） |
| 已有 | **场景化短期记忆**：当前场景对话 + 前文 tail 衔接，`/sc` 切换场景并归档 |
| 已有 | **Hot Canon / Cold Archive**：`/a` + y/n 即时设定；`/sc` Cold 摘要 review + `synopsis.json` |
| 已有 | **纠错与预算**：`/u` `/f` 回滚与设定纠错；`/config` 字符预算裁剪与切换建议 |
| 已有 | **正文采纳与导出**：`manuscript/scene_XXX.md` 归档；`/export` 合并导出 |
| 已有 | **第一版 Web/API**：项目列表、项目打开、讨论 / 写作双轨项目页、`discussion/*` / `writing/*` 结构化接口、写作 SSE 流式返回、侧栏 Discussion Brief 工作区（同步状态 / 刷新 / 清空 / 人工编辑） |

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

### 4. 运行 CLI

```bash
python main.py --project my_novel
```

启动后在终端输入创作指示；输入 `quit`、`exit` 或 `q` 退出。项目不存在时将引导创建并填写世界观 meta。

### 5. 运行 Web/API（第一版）

```bash
export LNAGENT_PROJECTS_DIR="$(pwd)/projects"
python web_main.py
```

或者直接使用一键启动脚本：

```bash
# macOS / Linux
bash scripts/start-web.sh

# Windows PowerShell
pwsh -File scripts/start-web.ps1
```

也支持自定义 host / port / projects 目录：

```bash
bash scripts/start-web.sh --host 0.0.0.0 --port 9000 --projects-dir /path/to/projects
```

```powershell
pwsh -File scripts/start-web.ps1 -Host 0.0.0.0 -Port 9000 -ProjectsDir C:\path\to\projects
```

默认监听 `http://127.0.0.1:8000`。

可直接访问：

- 首页：`/`
- 项目页：`/projects/<project_id>`
- 项目列表 API：`/api/projects`

第一版 Web/API 特性：

- 启动时不要求预先传入 `project_id`
- 通过 `project_id` 路径参数访问具体项目
- 项目页支持“讨论 / 写作”模式切换，并显式区分讨论消息与写作候选正文
- 提供 `discussion/get`、`discussion/send`、`discussion/refresh`、`discussion/clear` 与 `writing/send(/stream)` 双轨接口
- 侧栏常驻 `Discussion Brief` 工作区：展示待办、约束、待解问题，区分空态 / 待刷新 / 已同步 / 原始讨论已清空等状态；刷新、清空与人工编辑操作归属 brief 面板
- 保留显式确认语义：`adopt`、`fix`、`scene switch` 仍分为 prepare / commit
- `POST /api/projects/<id>/send/stream` 支持 SSE 流式返回
- SSE 前端断连后，后端仍继续完成本轮 LLM 生成；重新拉取 `session` 可看到完整 `last_candidate`
- 仍以 `JsonMemoryStore` 为持久化真源

已知限制：

- 暂无鉴权 / 多用户隔离
- 当前为最小页面壳，不包含富文本编辑体验
- 采用进程内 Session Registry，重启 Web 进程后未 checkpoint 的内存态不会保留
- CLI 入口仍保持原有单轨工作流；当前双轨入口主要在 Web/API 中
- 暂未引入 SQLite 查询层或 RAG-lite

### CLI 命令

作者通过**显式命令**控制记忆写入；**记忆存储对用户无感知**（JSON 由系统管理，不直接编辑文件）。

| 命令 | 别名 | 说明 |
|------|------|------|
| `/adopt` | `/a` | 编辑并采纳上一轮输出；Hot Canon diff **y/n** 确认 |
| `/scene` | `/sc` | 结束场景（须至少一次 `/a`）；Cold 摘要全文 review |
| `/undo` | `/u` | 撤销最后一次 adopt；正文 + Hot **一并回滚** |
| `/fix` | `/f` | 设定纠错（多行 + `EOF` 输入意图），仅改 Hot Canon（diff **y/n**） |
| `/canon` | `/c` | 查看 Hot Canon 摘要 |
| `/config` | — | 查看/修改项目配置（预算、切换建议阈值等） |
| `/export` | — | 合并导出全书正文（默认 `exports/YYYY-MM-DD.md`） |
| `/help` | `/h` | 命令帮助 |
| `/reject` | `/r` | Cold review 时丢弃提案 |
| `quit` / `exit` / `q` | — | 退出 |

Agent 以**启发式**建议切换场景，但**不会自动执行** `/sc`。

## 项目结构

```
LNAgent/
├── main.py              # CLI 入口
├── web_main.py          # Web/HTTP 入口（第一版）
├── lnagent/
│   ├── bootstrap.py     # CLI / Web 共享初始化
│   ├── project_index.py # 项目索引扫描
│   ├── app_service.py   # Web 服务层
│   ├── session_registry.py # 进程内 Session Registry
│   ├── web/             # 最小 Web 应用
│   ├── config.py        # 环境变量配置
│   ├── llm.py           # 模型初始化
│   ├── session.py       # 多轮会话（NovelSession）
│   ├── memory/          # 记忆存储、Prompt、Hot/Cold 抽取
│   ├── cli/             # /a、/c、/sc 等命令
│   └── chat.py          # 单轮对话客户端（库用）
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

- [x] 多轮会话与场景化短期记忆（当前场景 + 前文 tail 衔接）
- [x] Hot Canon（`/a` + y/n）与 Cold Archive（`/sc` + 摘要 review + `synopsis.json`）
- [x] 按场景正文归档（`manuscript/scene_XXX.md`）与 `/sc` 场景切换
- [x] `/undo`、`/fix` 纠错命令（Phase 4）
- [x] Prompt 字符预算裁剪与 `/config` 项目配置（Phase 5）
- [x] `/export` 全书导出与 `--meta` JSON 开书（Phase 6）
- [x] 第一版 Web/API（项目列表、会话接口、最小页面壳）
- [x] Web 前端 MVP 完善（undo/export/config、结构化侧栏、loading）
- [x] Web 流式 send（SSE token 推送）
- [x] 讨论 / 写作双轨 Web/API 与项目页 toggle（D0–D7）
- [x] Web Brief 工作空间 schema 定型（B0）
- [x] Web Brief 只读面板收口（B1）
- [x] Web Brief 人工编辑（B2）
- [ ] [可配置的文风与叙事模板](docs/features/style-template-implementation-plan.md)（S0–S2 计划已定稿）
- [ ] 向量 RAG 检索（Phase 7+，MVP 不做）

## 设计文档

- [记忆架构](docs/features/memory-architecture.md) — 设计共识与 CLI 约定
- [待讨论项](docs/features/open-questions.md) — 尚未拍板的问题 backlog
- [记忆 MVP 计划](docs/features/memory-mvp-plan.md) — 分阶段实现路线（Phase 0–6 已完成）
- [Web/API 第一版实施计划](docs/features/web-api-implementation-plan.md) — W0–W7 已实现，含阶段验收与限制记录
- [讨论 / 写作双轨设计](docs/features/discussion-writing-dual-track-design.md) — 双 prompt / 双存储 / 双 API 设计边界
- [讨论 / 写作双轨实施计划](docs/features/discussion-writing-dual-track-implementation-plan.md) — D0–D7 已实现（CLI 暂保持单轨）
- [Web Brief 工作空间实施计划](docs/features/web-brief-workspace-plan.md) — B0–B2 已实现；B3 保留给后续增强

## 许可证

待定。
