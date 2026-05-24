# LNAgent

**Light Novel Agent** — 通过向大模型提问或下达指示，生成完全自定义的轻小说。

## 简介

LNAgent 是一个面向轻小说创作的 AI Agent 项目。你可以用自然语言描述世界观、角色、情节走向与文风偏好，由大模型协助续写、扩写或从零生成章节内容。

当前版本提供基于 LangChain 的命令行对话入口，作为后续小说生成能力的基础框架。

## 功能

- **自定义创作**：通过提示词控制题材、设定与叙事风格（规划中）
- **CLI 对话**：命令行单轮问答，快速验证模型连通性与提示效果
- **OpenAI 兼容 API**：支持官方 OpenAI 及任意兼容接口（如本地部署、第三方网关）

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
python main.py
```

启动后在终端输入问题或创作指示；输入 `quit`、`exit` 或 `q` 退出。

## 项目结构

```
LNAgent/
├── main.py              # CLI 入口
├── lnagent/
│   ├── config.py        # 环境变量配置
│   ├── llm.py           # 模型初始化
│   └── chat.py          # 对话客户端
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

- [ ] 多轮会话与上下文记忆
- [ ] 角色 / 世界观 / 大纲等结构化设定管理
- [ ] 章节生成、续写与导出
- [ ] 可配置的文风与叙事模板

## 许可证

待定。
