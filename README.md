# Mmode-Magent--Eco-RS

基于多 Agent 的电商推荐系统 Python 实现。系统支持网页对话推荐、图片理解推荐、用户历史行为推荐、商品向量召回、用户向量召回、库存过滤、营销文案生成和数据生成。

## 功能概览

- 对话推荐：用户在网页端输入购物需求，系统返回推荐商品。
- 图片推荐：用户上传图片后，由多模态 Agent 识别图片内容，再进行商品召回。
- 两种召回模式：
  - `query_embedding`：根据用户当前问题或图片识别结果生成 embedding，在 Milvus 中召回相似商品。
  - `user_embedding`：根据用户历史交互形成用户 embedding，再召回相似商品。
- 数据生成：使用配置的 LLM 生成商品、用户、行为数据。
- 向量生成：商品使用 `title + description` 生成 embedding；用户使用交互商品 embedding 的加权平均表示。
- 数据存储：
  - SQLite：商品、库存、用户、用户行为等结构化数据。
  - Milvus：商品 embedding 和用户 embedding。

## 目录结构

```text
.
├── agents/              # 各类 Agent：用户画像、商品推荐、图片理解、库存、文案
├── config/              # 配置读取
├── data_generation/     # LLM 数据生成与向量种子流程
├── database/            # SQLAlchemy 数据模型和连接
├── models/              # Pydantic 数据结构
├── orchestrator/        # 多 Agent 编排
├── repositories/        # 商品、库存、用户行为数据访问层
├── services/            # embedding、Milvus、召回、指标、A/B 测试等服务
├── static/              # 网页聊天界面
├── tests/               # 测试
├── main.py              # FastAPI 入口
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量示例
└── .env.sample          # 无密钥环境变量模板
```

## 环境要求

- Python 3.10+
- Redis
- Milvus
- 可兼容 OpenAI SDK 的 LLM/Embedding 服务，例如阿里云百炼 DashScope compatible mode

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置环境变量

复制示例配置：

```bash
cp .env.sample .env
```

然后编辑 `.env`，至少填写：

```env
ECOM_LLM_API_KEY=你的API_KEY
ECOM_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ECOM_LLM_MODEL=qwen-vl-max

ECOM_EMBEDDING_API_KEY=你的API_KEY
ECOM_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ECOM_EMBEDDING_MODEL=text-embedding-v4
ECOM_EMBEDDING_DIMENSION=1024
```

注意：不要提交 `.env` 文件，仓库中的 `.gitignore` 已经默认忽略它。

## 启动依赖服务

需要先启动 Redis 和 Milvus。示例端口：

```env
ECOM_REDIS_URL=redis://localhost:6379/0
ECOM_MILVUS_HOST=localhost
ECOM_MILVUS_PORT=19530
```

如果你使用 Docker Compose，可以在项目根目录准备 Redis 和 Milvus 服务；如果只使用本仓库内容，需要自行启动对应服务。

## 生成演示数据

运行：

```bash
python data_generation/run_seed.py
```

流程会：

1. 调用 `ECOM_DATA_GENERATION_MODEL` 生成商品和用户行为。
2. 清空并重建 SQLite 中的商品、库存、用户、行为数据。
3. 使用 `ECOM_EMBEDDING_MODEL` 生成商品 embedding。
4. 根据用户行为的 `weight` 对交互商品 embedding 加权平均，生成用户 embedding。
5. 清空并重建 Milvus 中的商品向量集合和用户向量集合。

生成完成后会输出类似：

```text
{
  "products_saved": 160,
  "product_embeddings_indexed": 160,
  "users_saved": 5,
  "user_embeddings_indexed": 5
}
```

## 导出可读数据

如果想查看 SQLite 中的商品和用户文本数据：

```bash
python export_generated_data.py
```

会生成：

```text
generated_data.json
```

## 启动 Web 服务

```bash
python main.py
```

浏览器打开：

```text
http://127.0.0.1:8000/
```

网页端支持：

- 文字对话推荐
- 上传图片并基于图片内容推荐

## 推荐流程

### 文字推荐

```text
用户输入
-> RecallDecisionAgent 判断召回模式
-> query_embedding 或 user_embedding
-> Milvus 召回 product_id
-> SQLite 查询商品详情和库存
-> 商品排序
-> 营销文案生成
-> 返回网页
```

### 图片推荐

```text
上传图片
-> ImageUnderstandingAgent 识别图片内容
-> 生成适合召回的中文 query
-> query embedding
-> Milvus 召回相似商品
-> SQLite 补全商品详情
-> 返回推荐结果
```

当前图片推荐不是直接使用图像向量，而是先由多模态 LLM 将图片转为文本描述，再使用文本 embedding 进行向量召回。

### 用户历史推荐

当用户明确表达“根据最近看过、浏览历史、猜你喜欢”等意图时，会使用 `user_embedding`。

用户 embedding 由用户交互过的商品 embedding 加权平均得到：

```text
user_embedding =
sum(product_embedding_i * behavior_weight_i) / sum(behavior_weight_i)
```

## 常见问题

### 为什么 `.env` 没有上传？

`.env` 包含 API key 等敏感信息，不能上传。请使用 `.env.sample` 或 `.env.example` 作为模板。

### 为什么推荐为空？

常见原因：

- Milvus 没启动。
- 还没有运行 `data_generation/run_seed.py`。
- embedding 生成失败。
- 商品库中没有对应语义的商品。
- 当前用户没有用户 embedding，但问题要求根据历史推荐。

### 为什么 GitHub 上没有数据库文件？

本地 SQLite 数据库属于运行时数据，默认不上传。可以通过 `data_generation/run_seed.py` 重新生成。

## 测试

```bash
pytest
```

