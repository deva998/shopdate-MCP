"""Job-scoped idle-sleep hint. Never changes plans, display or manual sleep."""
import os

CONTINUOUS=0x80000000
SYSTEM_REQUIRED=0x00000001

class SystemAwake:
    def __init__(self,*,set_state=None):
        self.call=set_state;self.previous=None
        self.state={'supported':os.name=='nt' or set_state is not None,'acquired':False,'released':False}

    def __enter__(self):
        if not self.state['supported']:return self.state
        try:
            if self.call is None:
                import ctypes
                self.call=ctypes.WinDLL('kernel32',use_last_error=True).SetThreadExecutionState
                self.call.argtypes=[ctypes.c_uint];self.call.restype=ctypes.c_uint
            previous=self.call(CONTINUOUS|SYSTEM_REQUIRED)
            if previous:
                self.previous=int(previous);self.state['acquired']=True
            else:self.state['error']='SetThreadExecutionState returned NULL'
        except Exception as exc:self.state['error']=str(exc)
        return self.state

    def __exit__(self,*_):
        if self.previous is not None:
            try:
                # Preserve an outer lease on the same synchronous thread.
                self.state['released']=bool(self.call(self.previous|CONTINUOUS))
                if not self.state['released']:self.state['release_error']='execution state restore failed'
            except Exception as exc:self.state['release_error']=str(exc)
        return False
