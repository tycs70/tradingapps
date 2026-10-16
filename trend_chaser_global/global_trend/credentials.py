"""Optional token persistence protected for the current Windows user by DPAPI."""
import ctypes
import os
from pathlib import Path
import tempfile

HEADER=b'GLOBAL_CTRADER_DPAPI_V1\n'


class _DataBlob(ctypes.Structure):
    _fields_=[('cbData',ctypes.c_uint32),('pbData',ctypes.POINTER(ctypes.c_ubyte))]


class WindowsDPAPI:
    available=os.name=='nt'

    def _crypt(self,value: bytes,protect: bool) -> bytes:
        if not self.available:
            raise OSError('Remember token requires Windows user protection.')
        crypt32=ctypes.WinDLL('crypt32',use_last_error=True)
        kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
        operation=crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        operation.argtypes=[ctypes.POINTER(_DataBlob),
                            ctypes.c_wchar_p if protect else ctypes.POINTER(ctypes.c_wchar_p),
                            ctypes.POINTER(_DataBlob),ctypes.c_void_p,ctypes.c_void_p,
                            ctypes.c_uint32,ctypes.POINTER(_DataBlob)]
        operation.restype=ctypes.c_int
        kernel32.LocalFree.argtypes=[ctypes.c_void_p]
        kernel32.LocalFree.restype=ctypes.c_void_p
        buffer=(ctypes.c_ubyte*len(value)).from_buffer_copy(value)
        source=_DataBlob(len(value),buffer);result=_DataBlob()
        try:
            # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide protection flag.
            if not operation(ctypes.byref(source),'Trend Chaser Global credentials' if protect else None,
                             None,None,None,1,ctypes.byref(result)):
                raise OSError('Windows could not protect or restore the saved token.')
            return ctypes.string_at(result.pbData,result.cbData)
        finally:
            if result.pbData:kernel32.LocalFree(ctypes.cast(result.pbData,ctypes.c_void_p))

    def protect(self,value: bytes) -> bytes:return self._crypt(value,True)

    def unprotect(self,value: bytes) -> bytes:return self._crypt(value,False)


class TokenStore:
    def __init__(self,path: Path,cipher=None):
        self.path=Path(path)
        self.cipher=cipher if cipher is not None else WindowsDPAPI()

    @property
    def available(self):return self.cipher.available

    def save(self,token: str):
        if not token or len(token)>65536 or any(c.isspace() for c in token):
            raise OSError('Unable to save this access token.')
        # Protect before creating any file. There is no plaintext fallback.
        protected=self.cipher.protect(token.encode('utf-8'))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.global-credentials-',suffix='.tmp',dir=self.path.parent)
        try:
            with os.fdopen(fd,'wb') as file:
                file.write(HEADER+protected);file.flush();os.fsync(file.fileno())
            os.replace(temp,self.path)
        finally:
            Path(temp).unlink(missing_ok=True)

    def load(self) -> str | None:
        try:
            if self.path.stat().st_size>1048576:raise OSError('Saved token is unavailable.')
            value=self.path.read_bytes()
        except FileNotFoundError:return None
        if not value.startswith(HEADER):raise OSError('Saved token is unavailable.')
        try:
            token=self.cipher.unprotect(value[len(HEADER):]).decode('utf-8')
        except (OSError,UnicodeError):raise OSError('Saved token is unavailable.') from None
        if not token or len(token)>65536 or any(c.isspace() for c in token):
            raise OSError('Saved token is unavailable.')
        return token

    def clear(self):self.path.unlink(missing_ok=True)


class CredentialStore:
    """Memory first; optional user-scoped DPAPI retention with no plaintext path."""
    _fields={'client_id','client_secret','redirect_uri','access_token','refresh_token','expires_at','account_id'}

    def __init__(self,path,cipher=None):
        self.path=Path(path);self.cipher=cipher if cipher is not None else WindowsDPAPI()
        self._store=TokenStore(self.path,self.cipher);self._memory=None;self.warning=''

    @property
    def available(self):return self.cipher.available

    def save(self,data,remember=False):
        import base64,json
        self._memory={k:v for k,v in data.items() if k in self._fields}
        self.warning=''
        try:
            if remember:
                raw=json.dumps(self._memory,allow_nan=False,separators=(',',':')).encode()
                self._store.save(base64.b64encode(raw).decode('ascii'))
            else:self._store.clear()
            return True
        except (OSError,ValueError,TypeError):
            self.warning='Credentials remain in memory, but protected retention could not be updated.'
            return False

    def load(self):
        import base64,json
        if self._memory is not None:return dict(self._memory)
        try:
            raw=self._store.load()
            if raw is None:return None
            data=json.loads(base64.b64decode(raw,validate=True))
            if not isinstance(data,dict) or set(data)-self._fields:raise ValueError()
            if any(not isinstance(v,(str,int,float,type(None))) for v in data.values()):raise ValueError()
            self._memory=data
            return dict(data)
        except (OSError,ValueError,TypeError,UnicodeError):
            self.warning='Saved credentials are unavailable. Authorize again.'
            return None

    def clear(self):
        self._memory=None;self.warning='';self._store.clear()
