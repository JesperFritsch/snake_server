from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from importlib.resources import files

def configure_static_files(app: FastAPI):
    """ Mount the static files for the client and the protobuf files """
    protodir = files('snake_sim').joinpath('protobuf')
    static_dir = files('snake_server').joinpath('static')
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount("/protobuf", StaticFiles(directory=protodir), name="protobuf")


def serve_root():
    static_dir = files('snake_server').joinpath('static')
    return FileResponse(static_dir.joinpath(("index.html")))
