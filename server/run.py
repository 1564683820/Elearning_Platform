import uvicorn, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Starting E-Learning API Server on http://0.0.0.0:8000")
print(f"Working dir: {os.getcwd()}")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True,
        # 重载延迟（秒）：Windows 上文件系统时间戳精度不足导致误报，
        # 加大延迟让误报稳定，避免无限重载循环卡死服务器。
        reload_delay=3.0,
        # 仅监控 .py 文件变更，忽略 .pyc / .json / .log 等运行时文件
        reload_includes=["*.py"],
        # 仅监控代码目录，排除运行时写入数据的目录：
        #   app/data/ — BM25 索引持久化
        #   app/uploads/ — 用户上传文件
        #   app/templates/ — 静态模板
        reload_dirs=[
            "app/api",
            "app/core",
            "app/db",
            "app/middleware",
            "app/models",
            "app/ppt_generator",
            "app/routers",
            "app/schemas",
            "app/services",
            "app/tasks",
            "app/utils",
        ],
    )
