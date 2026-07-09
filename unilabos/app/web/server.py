"""
Web服务器模块

提供Web服务器功能，网页信息服务 + mqtt代替
"""

import webbrowser

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from unilabos.utils.fastapi.log_adapter import setup_fastapi_logging
from unilabos.utils.log import info, error
from unilabos.app.web.api import setup_api_routes
from unilabos.app.web.pages import setup_web_pages

# 创建FastAPI应用
app = FastAPI(
    title="UniLab API",
    description="UniLab API Service",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# 创建页面路由
pages = None
# Layout Optimizer 路由在模块加载时即注册
# 确保 uvicorn 直接加载 server:app 和通过 unilab CLI 启动两种方式均可用
try:
    from unilabos.app.web.routers.layout import layout_router
    app.include_router(layout_router, prefix="/api/v1")
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("Layout optimizer routes not loaded: %s", _e)

# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Serve static files from unilabos/app/web/static/
import os as _os
_static_dir = _os.path.join(_os.path.dirname(__file__), "static")
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# 挂载设备 mesh 文件（供 Three.js URDF Loader 通过 HTTP 访问 STL 文件）
_mesh_dir = _os.path.join(_os.path.dirname(__file__), "..", "..", "device_mesh")
_mesh_dir = _os.path.abspath(_mesh_dir)
if _os.path.isdir(_mesh_dir):
    app.mount("/meshes", StaticFiles(directory=_mesh_dir), name="meshes")


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    """
    记录HTTP请求日志的中间件

    Args:
        request: 当前HTTP请求对象
        call_next: 下一个处理函数

    Returns:
        Response: HTTP响应对象
    """
    # # 打印请求信息
    # info(f"[Web] Request: {request.method} {request.url}", stack_level=1)
    # debug(f"[Web] Headers: {request.headers}", stack_level=1)
    #
    # # 使用日志模块记录请求体（如果需要）
    # body = await request.body()
    # if body:
    #     debug(f"[Web] Body: {body}", stack_level=1)

    # 调用下一个中间件或路由处理函数
    response = await call_next(request)

    # # 打印响应信息
    # info(f"[Web] Response status: {response.status_code}", stack_level=1)

    return response


def setup_server() -> FastAPI:
    """
    设置服务器

    Returns:
        FastAPI: 配置好的FastAPI应用实例
    """
    global pages

    # 创建页面路由
    if pages is None:
        pages = app.router

    # 设置API路由
    setup_api_routes(app)

    # 设置页面路由
    try:
        setup_web_pages(pages)
        info("[Web] 已加载Web UI模块")
    except ImportError as e:
        info(f"[Web] 未找到Web页面模块: {str(e)}")
    except Exception as e:
        error(f"[Web] 加载Web页面模块时出错: {str(e)}")

    return app


def start_server(host: str = "0.0.0.0", port: int = 8002, open_browser: bool = True) -> bool:
    """
    启动服务器

    Args:
        host: 服务器主机
        port: 服务器端口
        open_browser: 是否自动打开浏览器

    Returns:
        bool: True if restart was requested, False otherwise
    """
    import threading
    import time
    from uvicorn import Config, Server

    # 设置服务器
    setup_server()

    # 配置日志
    log_config = setup_fastapi_logging()

    # 启动前打开浏览器
    if open_browser:
        # noinspection HttpUrlsUsage
        url = f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}/status"
        info(f"[Web] 正在打开浏览器访问: {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            error(f"[Web] 无法打开浏览器: {str(e)}")

    # 启动服务器
    info(f"[Web] 启动FastAPI服务器: {host}:{port}")

    # 使用支持重启的模式
    config = Config(app=app, host=host, port=port, log_config=log_config)
    server = Server(config)

    # 启动服务器线程
    server_thread = threading.Thread(target=server.run, daemon=True, name="uvicorn_server")
    server_thread.start()

    info("[Web] Server started, monitoring for restart requests...")

    # 监控重启标志
    import unilabos.app.main as main_module

    while server_thread.is_alive():
        if hasattr(main_module, "_restart_requested") and main_module._restart_requested:
            info(
                f"[Web] Restart requested via WebSocket, reason: {getattr(main_module, '_restart_reason', 'unknown')}"
            )
            main_module._restart_requested = False

            # 停止服务器
            server.should_exit = True
            server_thread.join(timeout=5)

            info("[Web] Server stopped, ready for restart")
            return True

        time.sleep(1)

    return False



# Auto-initialize when loaded by uvicorn directly (e.g. uvicorn server:app)
_setup_done = False
def _auto_setup():
    global _setup_done
    if not _setup_done:
        _setup_done = True
        setup_server()

_auto_setup()

# 当脚本直接运行时启动服务器
if __name__ == "__main__":
    start_server()
