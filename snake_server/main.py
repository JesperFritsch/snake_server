import uvicorn
import sys
import logging
from pathlib import Path

from fastapi import FastAPI

from contextlib import asynccontextmanager

from snake_server.app.routers import api_routes, navigation_routes, websocket_routes
from snake_server.app.services.nav_services import configure_static_files
from snake_server.cli import cli
from snake_server.logging import setup_loggers
from snake_server.process_pool.process_pool import SnakeProcessPool
from snake_server.source_manager.stream_source_manager import StreamSourceManager


log = logging.getLogger(Path(__file__).stem)

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = SnakeProcessPool()
    try:
        await pool.start_monitor()
        yield
    except KeyboardInterrupt:
        pass
    finally:
        log.info("life span cleanup")
        await pool.shutdown()
        StreamSourceManager().cleanup()


app = FastAPI(lifespan=lifespan)

app.include_router(api_routes.router, prefix="/api", tags=["API"])
app.include_router(navigation_routes.router, tags=["NAVIGATION"])
app.include_router(websocket_routes.router, prefix="/ws", tags=["WEBSOCKET"])
configure_static_files(app)


def main():
    args = cli(sys.argv[1:])
    setup_loggers(args.log_level)
    try:
        uvicorn.run("snake_server.main:app", host=args.host, port=args.port, reload=args.dev)
    except KeyboardInterrupt:
        log.info("Server stopped by user")

if __name__ == "__main__":
    main()
