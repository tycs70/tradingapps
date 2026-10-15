import socket
import ssl
import struct
import subprocess
import tempfile
from pathlib import Path
import threading
import time
import unittest
from global_trend.transport import FrameDecoder, encode_frame, ProtoClient, TransportError
from global_trend.protocol import OA, Common, encode_message, decode_message


class FramingTest(unittest.TestCase):
    def test_fragmented_and_coalesced_frames(self):
        wire=encode_frame(b'abc')+encode_frame(b'defgh')
        d=FrameDecoder();out=[]
        for byte in wire:out.extend(d.feed(bytes([byte])))
        self.assertEqual(out,[b'abc',b'defgh'])
        self.assertEqual(FrameDecoder().feed(wire),[b'abc',b'defgh'])

    def test_zero_and_oversized_frames_fail_before_body(self):
        for length in [0,16*1024*1024+1]:
            with self.assertRaises(ValueError):FrameDecoder().feed(struct.pack('!I',length))


class TLSFixture:
    def __init__(self,cert,key,handler):
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.socket.listen(1)
        self.port=self.socket.getsockname()[1];self.handler=handler
        self.cert,self.key=cert,key;self.errors=[]
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,self.key)
        try:
            self.socket.settimeout(3)
            raw,_=self.socket.accept()
            with raw:
                with context.wrap_socket(raw,server_side=True) as conn:
                    conn.settimeout(3);self.handler(conn)
        except (OSError,ssl.SSLError):pass
        except Exception as exc:self.errors.append(exc)
        finally:self.socket.close()
    def close(self):
        self.socket.close();self.thread.join(4)
        if self.errors:raise self.errors[0]


class TransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        cls.cert=str(root/'cert.pem');cls.key=str(root/'key.pem')
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-keyout',cls.key,'-out',cls.cert,'-subj','/CN=localhost',
                        '-addext','subjectAltName=DNS:localhost'],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def context(self):return ssl.create_default_context(cafile=self.cert)
    def client(self,server,**kwargs):
        return ProtoClient('127.0.0.1',server.port,server_hostname='localhost',
                           ssl_context=kwargs.pop('ssl_context',self.context()),**kwargs)

    def test_verified_request_and_response_correlation(self):
        def handler(conn):
            d=FrameDecoder()
            while True:
                data=conn.recv(65536)
                if not data:return
                for body in d.feed(data):
                    ident,msg=decode_message(body)
                    conn.sendall(encode_frame(encode_message(OA.ProtoOAApplicationAuthRes(),ident)))
                    return
        server=TLSFixture(self.cert,self.key,handler);client=self.client(server)
        try:
            response=client.request(OA.ProtoOAApplicationAuthReq(clientId='id',clientSecret='test-secret'))
            self.assertIsInstance(response,OA.ProtoOAApplicationAuthRes)
        finally:client.close();server.close()

    def test_wrong_hostname_and_untrusted_chain_fail(self):
        for name,context in [('wrong.invalid',self.context()),('localhost',ssl.create_default_context())]:
            server=TLSFixture(self.cert,self.key,lambda c:c.recv(1))
            client=ProtoClient('127.0.0.1',server.port,server_hostname=name,ssl_context=context)
            try:
                with self.assertRaises(ssl.SSLCertVerificationError):client.connect()
            finally:client.close();server.close()

    def test_timeout_and_disconnect_release_pending_waiters(self):
        server=TLSFixture(self.cert,self.key,lambda c:(c.recv(65536),time.sleep(.3)))
        client=self.client(server)
        try:
            with self.assertRaises(TransportError):
                client.request(OA.ProtoOASymbolsListReq(ctidTraderAccountId=123),timeout=.05)
            self.assertEqual(client.pending_count,0)
        finally:client.close();server.close()

    def test_api_errors_do_not_expose_response_secrets(self):
        def handler(conn):
            d=FrameDecoder()
            for body in d.feed(conn.recv(65536)):
                ident,_=decode_message(body)
                error=OA.ProtoOAErrorRes(errorCode='AUTH_ERROR',description='TOPSECRET',ctidTraderAccountId=123)
                conn.sendall(encode_frame(encode_message(error,ident)))
        server=TLSFixture(self.cert,self.key,handler);client=self.client(server)
        try:
            with self.assertRaises(TransportError) as caught:
                client.request(OA.ProtoOASymbolsListReq(ctidTraderAccountId=123))
            self.assertNotIn('TOPSECRET',str(caught.exception))
        finally:client.close();server.close()


if __name__=='__main__':unittest.main()
