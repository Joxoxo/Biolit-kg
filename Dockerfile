# BioLit-KG 部署镜像：一个容器同时提供网页和接口（Hugging Face Spaces 默认端口 7860）
#
# 多阶段构建：第 1 阶段用 Node 把 React 网页打包成静态文件；第 2 阶段只装 Python 运行环境，
# 把打包好的网页复制过来。最终镜像里没有 Node 和 node_modules，体积小很多。
#
# 本地测试：
#   docker build -t biolit-kg .
#   docker run -p 7860:7860 -e GEMINI_API_KEY=你的Key biolit-kg
#   然后打开 http://localhost:7860

# ---------- 第 1 阶段：打包前端 ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY app/package.json app/package-lock.json ./
RUN npm ci                                   # 严格按 package-lock.json 安装，保证版本一致
COPY app/ ./
RUN npm run build                            # 产出 /web/dist

# ---------- 第 2 阶段：Python 运行环境 ----------
FROM python:3.14-slim
# Hugging Face Spaces 要求用 uid 1000 的普通用户运行
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# 先只复制依赖清单再安装：代码改动时这一层能用缓存，不用每次重装依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
# 不把 biolit 安装进 site-packages，而是直接从 src 运行：
# 代码里的项目根目录是按 db.py 的位置往上找两级得到的，装进 site-packages 后会指错，找不到数据文件
ENV PYTHONPATH=/home/user/app/src
COPY configs ./configs
# 运行时需要的数据：数据库、图谱、向量索引、模型调用缓存（含预热的示例问题）、说明书比对结果
COPY data/biolit.db ./data/biolit.db
COPY data/processed/graph.json data/processed/index.npz data/processed/llm_cache.db data/processed/label_crosscheck.json ./data/processed/
COPY --from=web /web/dist ./app/dist

RUN chown -R user:user /home/user/app        # 缓存数据库运行时要写入
USER user
ENV ACTIVE_PROMPT_VERSION=v5 GEMINI_MODEL=gemini-3.5-flash-lite
EXPOSE 7860
CMD ["uvicorn", "biolit.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
