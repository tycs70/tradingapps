"""Certificate-verified framed TLS; credentials and wire bytes never enter logs."""
import queue
import socket
import ssl
import struct
import threading
import time
import uuid
from .protocol import Common, OA, encode_message, decode_message

MAX_FRAME=16*1024*1024
HEARTBEAT_SECONDS=10


class TransportError(RuntimeError):
    requires_authorization=False
    def __init__(self,message,code='network'):
        super().__init__(message);self.code=code

class AuthorizationError(TransportError):
    requires_authorization=True
    def __init__(self,message='cTrader authorization is no longer valid. Authorize the application again.'):
        super().__init__(message,code='authorization')

class RateLimitError(TransportError):
    def __init__(self,retry_after,payload_type):
        self.retry_after=max(1,float(retry_after));self.payload_type=int(payload_type)
        super().__init__('cTrader temporarily blocked this request type. Waiting before retrying.')


def encode_frame(payload):
    if not 0<len(payload)<=MAX_FRAME:raise ValueError('Invalid protocol frame length.')
    return struct.pack('!I',len(payload))+payload


class FrameDecoder:
    def __init__(self):self.buffer=bytearray()
    def feed(self,data):
        self.buffer.extend(data);out=[]
        while len(self.buffer)>=4:
            size=struct.unpack('!I',self.buffer[:4])[0]
            if not 0<size<=MAX_FRAME:
                self.buffer.clear();raise ValueError('Invalid protocol frame length.')
            if len(self.buffer)<4+size:break
            out.append(bytes(self.buffer[4:4+size]));del self.buffer[:4+size]
        return out


class ProtoClient:
    def __init__(self,host='demo.ctraderapi.com',port=5035,server_hostname=None,ssl_context=None):
        self.host,self.port=host,port
        self.server_hostname=server_hostname or host
        self.context=ssl_context or ssl.create_default_context()
        if not self.context.check_hostname or self.context.verify_mode!=ssl.CERT_REQUIRED:
            raise ValueError('Verified TLS and hostname checking are required.')
        self._socket=None;self._thread=None;self._closed=threading.Event()
        self._connect_lock=threading.Lock();self._send_lock=threading.Lock()
        self._pending_lock=threading.Lock();self._pending={};self._callbacks=[]
        self._last_sent=time.monotonic()
        self._clock=time.monotonic;self._blocked_until={}

    @property
    def pending_count(self):
        with self._pending_lock:return len(self._pending)

    def subscribe(self,callback):self._callbacks.append(callback)

    def connect(self):
        with self._connect_lock:
            if self._closed.is_set():raise TransportError('Connection is closed.')
            if self._socket is not None:return
            raw=socket.create_connection((self.host,self.port),timeout=10)
            try:self._socket=self.context.wrap_socket(raw,server_hostname=self.server_hostname)
            except Exception:
                raw.close();raise
            self._socket.settimeout(1)
            self._thread=threading.Thread(target=self._receive,name='ctrader-tls',daemon=True)
            self._thread.start()

    def _send(self,message,ident=''):
        body=encode_frame(encode_message(message,ident))
        with self._send_lock:
            sock=self._socket
            if sock is None or self._closed.is_set():raise TransportError('cTrader connection is closed.')
            try:sock.sendall(body)
            except OSError:raise TransportError('Unable to send to cTrader.') from None
            self._last_sent=time.monotonic()

    def request(self,message,timeout=10.0):
        payload_type=int(message.payloadType)
        self._check_blocked(payload_type)
        self.connect();ident=uuid.uuid4().hex;result=queue.Queue(maxsize=1)
        with self._pending_lock:
            if len(self._pending)>=128:raise TransportError('Too many pending cTrader requests.')
            self._pending[ident]=result
        try:
            self._check_blocked(payload_type)
            self._send(message,ident)
            try:value=result.get(timeout=timeout)
            except queue.Empty:raise TransportError('cTrader request timed out.') from None
            if isinstance(value,Exception):raise value
            if isinstance(value,(OA.ProtoOAErrorRes,Common.ProtoErrorRes)):
                if value.errorCode=='BLOCKED_PAYLOAD_TYPE':
                    retry=value.retryAfter if isinstance(value,OA.ProtoOAErrorRes) and value.HasField('retryAfter') else 60
                    retry=max(1,int(retry))
                    with self._pending_lock:
                        self._blocked_until[payload_type]=max(self._blocked_until.get(payload_type,0),self._clock()+retry)
                    raise RateLimitError(retry,payload_type)
                if value.errorCode in ('OA_AUTH_TOKEN_EXPIRED','ACCOUNT_NOT_AUTHORIZED','RET_NO_SUCH_LOGIN',
                        'RET_ACCOUNT_DISABLED','CH_CLIENT_AUTH_FAILURE','CH_CLIENT_NOT_AUTHENTICATED',
                        'CH_ACCESS_TOKEN_INVALID','CH_CTID_TRADER_ACCOUNT_NOT_FOUND','CH_OA_CLIENT_NOT_FOUND'):
                    raise AuthorizationError()
                raise TransportError('cTrader rejected the request. Check authorization and account permissions.')
            return value
        finally:
            with self._pending_lock:self._pending.pop(ident,None)

    def _check_blocked(self,payload_type):
        with self._pending_lock:remaining=self._blocked_until.get(payload_type,0)-self._clock()
        if remaining>0:raise RateLimitError(remaining,payload_type)

    def _fail_pending(self):
        with self._pending_lock:
            pending=list(self._pending.values());self._pending.clear()
        for item in pending:
            try:item.put_nowait(TransportError('cTrader connection was interrupted.'))
            except queue.Full:pass

    def _receive(self):
        decoder=FrameDecoder();sock=self._socket;reason='remote_closed'
        try:
            while not self._closed.is_set():
                # Incoming quotes must not postpone the client's keepalive.
                if time.monotonic()-self._last_sent>=HEARTBEAT_SECONDS:
                    self._send(Common.ProtoHeartbeatEvent())
                try:data=sock.recv(65536)
                except socket.timeout:continue
                if not data:break
                for body in decoder.feed(data):
                    ident,message=decode_message(body)
                    if message is None:continue
                    if isinstance(message,Common.ProtoHeartbeatEvent):
                        self._send(Common.ProtoHeartbeatEvent());continue
                    with self._pending_lock:pending=self._pending.get(ident)
                    if pending is not None:
                        try:pending.put_nowait(message)
                        except queue.Full:pass
                    else:
                        for callback in tuple(self._callbacks):callback(message)
        except ssl.SSLError:reason='tls'
        except (OSError,TransportError):reason='socket'
        except ValueError:reason='protocol'
        except Exception:reason='processing'
        finally:
            unexpected=not self._closed.is_set();self._closed.set();self._fail_pending()
            if unexpected:
                for callback in tuple(self._callbacks):
                    try:callback(TransportError('cTrader connection was interrupted.',code=reason))
                    except Exception:pass
            try:sock.close()
            except OSError:pass

    def close(self):
        self._closed.set();self._fail_pending()
        sock=self._socket
        if sock:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            try:sock.close()
            except OSError:pass
        if self._thread and self._thread is not threading.current_thread():self._thread.join(2)
