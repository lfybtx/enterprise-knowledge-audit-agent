# Lesson 01: FastAPI 最小项目

这一阶段只做一件事：把后端服务跑起来。

## 你要理解的概念

如果你熟悉 Java 后端，可以这样类比：

| Java / Spring Boot | Python / FastAPI |
| --- | --- |
| `@RestController` | `@app.get()` / `@app.post()` |
| DTO / Request Body | Pydantic `BaseModel` |
| `application.yml` | `.env` |
| Maven/Gradle 依赖 | `requirements.txt` |
| Swagger UI | FastAPI 自动生成的 `/docs` |

## 当前项目结构

```text
enterprise-knowledge-audit-agent/
├─ app/
│  ├─ main.py                  # FastAPI 入口
│  ├─ data/sample_documents.json
│  └─ services/                # 检索和审计逻辑
├─ web/                        # 简单前端页面
├─ tests/                      # 后续测试
├─ scripts/run_evaluation.py   # 检索评测脚本
├─ requirements.txt            # Python 依赖
└─ README.md
```

## 第一次运行

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

打开：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/api/health`

## 本阶段验收标准

- `/api/health` 返回 `{"status":"ok", ...}`
- `/docs` 能看到 Swagger UI
- 首页能输入问题并看到证据引用

## 常见问题

### PowerShell 不允许激活虚拟环境

执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

然后重新执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 依赖下载失败

优先检查网络和代理。也可以尝试：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```
