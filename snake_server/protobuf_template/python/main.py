import grpc
from concurrent import futures
import time
import random
import os
import sys

import remote_snake_pb2
import remote_snake_pb2_grpc
import user_code

class RemoteSnakeServicer(remote_snake_pb2_grpc.RemoteSnakeServicer):
    def SetId(self, request, context):
        # Implement your logic here
        return remote_snake_pb2.Empty()

    def SetStartLength(self, request, context):
        # Implement your logic here
        return remote_snake_pb2.Empty()

    def SetStartPosition(self, request, context):
        # Implement your logic here
        return remote_snake_pb2.Empty()

    def SetInitData(self, request, context):
        # Implement your logic here
        self.user_code = user_code.UserCode(request)
        return remote_snake_pb2.Empty()

    def Update(self, request_iterator, context):
        ret = self.user_code.update(request)
        direction = remote_snake_pb2.Coord()
        direction.x = ret[0]
        direction.y = ret[1]
        return remote_snake_pb2.UpdateResponse(direction=direction)

def serve(server_path):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    remote_snake_pb2_grpc.add_RemoteSnakeServicer_to_server(RemoteSnakeServicer(), server)
    # create a socket file and change the mode to 777
    socket_path = server_path
    server.add_insecure_port(f'unix:{socket_path}')
    server.start()
    os.chmod(socket_path, 0o777)
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)
        if os.path.exists(socket_path):
            os.remove(socket_path)
    finally:
        server.stop(0)
        if os.path.exists(socket_path):
            os.remove(socket_path)


print(sys.argv)
server_path = sys.argv[1]
print(f"Starting server {server_path}")
serve(server_path)

