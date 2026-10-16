"""Official message schemas with a bounded, explicit envelope decoder."""
from google.protobuf.message import DecodeError
from . import OpenApiMessages_pb2 as OA
from . import OpenApiModelMessages_pb2 as Model
from . import OpenApiCommonMessages_pb2 as Common
from . import OpenApiCommonModelMessages_pb2 as CommonModel

_TYPES={}
for module in (OA,Common):
    for descriptor in module.DESCRIPTOR.message_types_by_name.values():
        cls=getattr(module,descriptor.name)
        if 'payloadType' in descriptor.fields_by_name:
            _TYPES[cls().payloadType]=cls


def encode_message(message,client_msg_id=''):
    if not message.IsInitialized():
        raise ValueError('Incomplete protocol message.')
    outer=Common.ProtoMessage(payloadType=message.payloadType,
                              payload=message.SerializeToString(),clientMsgId=client_msg_id)
    return outer.SerializeToString()


def decode_message(data):
    try:
        outer=Common.ProtoMessage.FromString(data)
        if not outer.IsInitialized():raise ValueError('Incomplete protocol envelope.')
        cls=_TYPES.get(outer.payloadType)
        if cls is None:return outer.clientMsgId,None
        message=cls.FromString(outer.payload)
        if not message.IsInitialized():raise ValueError('Incomplete protocol payload.')
        return outer.clientMsgId,message
    except DecodeError:
        raise ValueError('Invalid protocol message.') from None
