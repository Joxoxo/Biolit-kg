"""把项目上传到 Hugging Face Space（Docker 类型），Space 收到后会自动按 Dockerfile 构建并上线。

为什么要单独上传，而不是直接连 GitHub：数据库、向量索引等数据文件在 .gitignore 里，不在 GitHub 上，
但线上服务运行时需要它们。这个脚本从本地文件夹直接挑选需要的文件上传。

第一次部署前的准备（都在你自己的电脑和浏览器上完成）：
1. 在 huggingface.co 新建 Space：SDK 选 Docker，模板选 Blank
2. Space 的 Settings → Variables and secrets：添加 Secret，名字 GEMINI_API_KEY，值填你的 Key
3. 本地安装并登录：pip install huggingface_hub，然后运行 hf auth login，按提示粘贴你的 Hugging Face token
4. 先预热缓存：python scripts/warm_cache.py
5. 确认前端依赖锁文件是最新的：cd app; npm install; cd ..

运行（在 biolit-kg 文件夹下）：
    python scripts/deploy_space.py 你的用户名/space名
"""
import sys

from huggingface_hub import HfApi

from biolit.db import ROOT

INCLUDE = [
    "Dockerfile", ".dockerignore", "requirements.txt", "pyproject.toml",
    "src/**", "configs/**",
    "app/**",
    "data/biolit.db",
    "data/processed/graph.json", "data/processed/index.npz",
    "data/processed/llm_cache.db", "data/processed/label_crosscheck.json",
]
EXCLUDE = ["**/__pycache__/**", "app/node_modules/**", "app/dist/**", "**/*.pyc"]


def main():
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        sys.exit("用法：python scripts/deploy_space.py 你的用户名/space名")
    repo = sys.argv[1]
    missing = [p for p in INCLUDE if "*" not in p and not (ROOT / p).exists()]
    if missing:
        sys.exit(f"缺少文件：{missing}\n请先按本文件开头的步骤准备好数据。")

    api = HfApi()
    api.upload_folder(folder_path=ROOT, repo_id=repo, repo_type="space",
                      allow_patterns=INCLUDE, ignore_patterns=EXCLUDE,
                      commit_message="部署 BioLit-KG")
    # Space 的 README.md 开头必须有一段配置（sdk: docker、端口等），和 GitHub 上的 README 不同
    api.upload_file(path_or_fileobj=ROOT / "deploy" / "README_space.md", path_in_repo="README.md",
                    repo_id=repo, repo_type="space", commit_message="Space 说明")
    print(f"已上传。构建进度和日志：https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
