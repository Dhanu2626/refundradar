"""A stand-in for FastAPI, for the live demo only (tools/demo_engine/bridge.py).

The demo calls refundradar.webapp's route functions directly, so the route
decorators hand each function back unchanged, and HTTPException carries the
same status and detail the real one does.
"""


class HTTPException(Exception):
    def __init__(self, status_code: int, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda route: route

    post = get
