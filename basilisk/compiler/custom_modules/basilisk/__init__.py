# Runtime module for basilisk - this is the version that gets bundled into canisters
# It contains all types and decorators needed at runtime without complex relative imports

import sys
from typing import (
    Annotated,
    Any,
    Callable,
    Generator,
    Generic,
    NoReturn,
    Optional,
    ParamSpec,
    TypedDict,
    TypeVar,
    TypeAlias,
    Union,
)

# Principal class is included directly to avoid import issues
import zlib
import math
import base64
import hashlib
from enum import Enum

CRC_LENGTH_IN_BYTES = 4
HASH_LENGTH_IN_BYTES = 28
MAX_LENGTH_IN_BYTES = 29


class PrincipalClass(Enum):
    OpaqueId = 1
    SelfAuthenticating = 2
    DerivedId = 3
    Anonymous = 4


class Principal:
    def __init__(self, bytes: bytes = b""):
        self._len = len(bytes)
        self._bytes = bytes
        self.hex = str(self._bytes.hex()).upper()
        self._isPrincipal = True

    @staticmethod
    def management_canister():
        return Principal()

    @staticmethod
    def self_authenticating(pubkey: Union[str, bytes]):
        if isinstance(pubkey, str):
            pubkey = bytes.fromhex(pubkey)
        hash_ = hashlib.sha224(pubkey).digest()
        hash_ += bytes([PrincipalClass.SelfAuthenticating.value])
        return Principal(bytes=hash_)

    @staticmethod
    def anonymous():
        return Principal(bytes=b"\x04")

    @property
    def len(self):
        return self._len

    @property
    def bytes(self):
        return self._bytes

    @property
    def isPrincipal(self):
        return self._isPrincipal

    @staticmethod
    def from_str(s: str):
        s1 = s.replace("-", "")
        pad_len = math.ceil(len(s1) / 8) * 8 - len(s1)
        b = base64.b32decode(s1.upper().encode() + b"=" * pad_len)
        if len(b) < CRC_LENGTH_IN_BYTES:
            raise Exception("principal length error")
        p = Principal(bytes=b[CRC_LENGTH_IN_BYTES:])
        if not p.to_str() == s:
            raise Exception("principal format error")
        return p

    @staticmethod
    def from_hex(s: str):
        return Principal(bytes.fromhex(s.lower()))

    def to_str(self):
        checksum = zlib.crc32(self._bytes) & 0xFFFFFFFF
        b = b""
        b += checksum.to_bytes(CRC_LENGTH_IN_BYTES, byteorder="big")
        b += self.bytes
        s = base64.b32encode(b).decode("utf-8").lower().replace("=", "")
        ret = ""
        while len(s) > 5:
            ret += s[:5]
            ret += "-"
            s = s[5:]
        ret += s
        return ret

    def to_account_id(self, sub_account: int = 0):
        return AccountIdentifier.new(self, sub_account)

    def __repr__(self):
        return "Principal(" + self.to_str() + ")"

    def __str__(self):
        return self.to_str()


class AccountIdentifier:
    def __init__(self, hash: bytes) -> None:
        assert len(hash) == 32
        self._hash = hash

    def to_str(self):
        return "0x" + self._hash.hex()

    def __repr__(self):
        return "Account(" + self.to_str() + ")"

    def __str__(self):
        return self.to_str()

    @property
    def bytes(self) -> bytes:
        return self._hash

    @staticmethod
    def new(principal: Principal, sub_account: int = 0):
        sha224 = hashlib.sha224()
        sha224.update(b"\x0Aaccount-id")
        sha224.update(principal.bytes)

        sub_account = sub_account.to_bytes(32, byteorder="big")  # type: ignore
        sha224.update(sub_account)  # type: ignore
        hash = sha224.digest()
        checksum = zlib.crc32(hash) & 0xFFFFFFFF
        account = checksum.to_bytes(CRC_LENGTH_IN_BYTES, byteorder="big") + hash
        return AccountIdentifier(account)


# Type aliases
int64 = int
int32 = int
int16 = int
int8 = int

nat = int
nat64 = int
nat32 = int
nat16 = int
nat8 = int

float64 = float
float32 = float

text = str

T = TypeVar("T")
Opt = Optional[T]
Manual = Optional[T]
Alias = Annotated[T, None]

Tuple = tuple
Vec = list

Record = TypedDict
Variant = TypedDict

blob = bytes

null: TypeAlias = None
void: TypeAlias = None

reserved = Any
empty: TypeAlias = NoReturn

Async = Generator[Any, Any, T]

TimerId = Alias[nat64]
Duration = Alias[nat64]


class GuardResult(Variant, total=False):
    Ok: null
    Err: str


GuardType = Callable[..., GuardResult]


def query(
    _func: Optional[Callable[..., Any]] = None, *, guard: Optional[GuardType] = None
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]):
        return func

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def update(
    _func: Optional[Callable[..., Any]] = None, *, guard: Optional[GuardType] = None
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]):
        return func

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def canister(cls: T) -> T:
    return cls


def init(func: object):
    return func


def heartbeat(
    _func: Optional[Callable[..., Any]] = None, *, guard: Optional[GuardType] = None
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]):
        return func

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def pre_upgrade(
    _func: Optional[Callable[..., Any]] = None, *, guard: Optional[GuardType] = None
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]):
        return func

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def post_upgrade(func: object):
    return func


def inspect_message(
    _func: Optional[Callable[..., Any]] = None, *, guard: Optional[GuardType] = None
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]):
        return func

    if _func is None:
        return decorator
    else:
        return decorator(_func)


Query = Callable
Update = Callable
Oneway = Callable


class CallResult(Generic[T]):
    Ok: T
    Err: Optional[str]

    def __init__(self, Ok: T, Err: str):
        self.Ok = Ok
        self.Err = Err

    def notify(self) -> "NotifyResult": ...

    def with_cycles(self, cycles: nat64) -> "CallResult[T]": ...

    def with_cycles128(self, cycles: nat) -> "CallResult[T]": ...


class RejectionCode(Variant, total=False):
    NoError: null
    SysFatal: null
    SysTransient: null
    DestinationInvalid: null
    CanisterReject: null
    CanisterError: null
    Unknown: null


class NotifyResult(Variant, total=False):
    Ok: null
    Err: RejectionCode


class StableMemoryError(Variant, total=False):
    OutOfMemory: null
    OutOfBounds: null


class StableGrowResult(Variant, total=False):
    Ok: nat32
    Err: StableMemoryError


class Stable64GrowResult(Variant, total=False):
    Ok: nat64
    Err: StableMemoryError


FuncTuple = tuple[Principal, str]


def Func(callable: Callable[..., Any]) -> type[FuncTuple]:
    return FuncTuple


def get_first_called_function_name() -> str:
    first_frame = get_first_frame(sys._getframe())  # type: ignore
    return first_frame.f_code.co_name


def get_first_frame(current_frame: Any) -> Any:
    previous_frame = current_frame.f_back

    if previous_frame is None:
        return current_frame

    return get_first_frame(previous_frame)


class ic(Generic[T]):
    @staticmethod
    def accept_message():
        _basilisk_ic.accept_message()  # type: ignore

    @staticmethod
    def arg_data_raw() -> blob:
        return _basilisk_ic.arg_data_raw()  # type: ignore

    @staticmethod
    def arg_data_raw_size() -> nat32:
        return _basilisk_ic.arg_data_raw_size()  # type: ignore

    @staticmethod
    def call_raw(
        canister_id: Principal, method: str, args_raw: blob, payment: nat64
    ) -> CallResult[T]:
        return AsyncInfo(
            "call_raw", [canister_id, method, args_raw, payment]
        )  # type: ignore

    @staticmethod
    def call_raw128(
        canister_id: Principal, method: str, args_raw: blob, payment: nat
    ) -> CallResult[T]:
        return AsyncInfo(
            "call_raw128", [canister_id, method, args_raw, payment]
        )  # type: ignore

    @staticmethod
    def caller() -> Principal:
        return _basilisk_ic.caller()  # type: ignore

    @staticmethod
    def candid_encode(candid_string: str) -> blob:
        return _basilisk_ic.candid_encode(candid_string)  # type: ignore

    @staticmethod
    def candid_decode(candid_encoded: blob) -> str:
        return _basilisk_ic.candid_decode(candid_encoded)  # type: ignore

    @staticmethod
    def canister_balance() -> nat64:
        return _basilisk_ic.canister_balance()  # type: ignore

    @staticmethod
    def canister_balance128() -> nat:
        return _basilisk_ic.canister_balance128()  # type: ignore

    @staticmethod
    def clear_timer(id: TimerId) -> None:
        return _basilisk_ic.clear_timer(id)  # type: ignore

    @staticmethod
    def data_certificate() -> Opt[blob]:
        return _basilisk_ic.data_certificate()  # type: ignore

    @staticmethod
    def id() -> Principal:
        return _basilisk_ic.id()  # type:ignore

    @staticmethod
    def method_name() -> str:
        return _basilisk_ic.method_name()  # type:ignore

    @staticmethod
    def msg_cycles_accept(max_amount: nat64) -> nat64:
        return _basilisk_ic.msg_cycles_accept(max_amount)  # type: ignore

    @staticmethod
    def msg_cycles_accept128(max_amount: nat) -> nat:
        return _basilisk_ic.msg_cycles_accept128(max_amount)  # type: ignore

    @staticmethod
    def msg_cycles_available() -> nat64:
        return _basilisk_ic.msg_cycles_available()  # type: ignore

    @staticmethod
    def msg_cycles_available128() -> nat:
        return _basilisk_ic.msg_cycles_available128()  # type: ignore

    @staticmethod
    def msg_cycles_refunded() -> nat64:
        return _basilisk_ic.msg_cycles_refunded()  # type: ignore

    @staticmethod
    def msg_cycles_refunded128() -> nat:
        return _basilisk_ic.msg_cycles_refunded128()  # type: ignore

    @staticmethod
    def notify_raw(
        canister_id: Principal, method: str, args_raw: blob, payment: nat
    ) -> NotifyResult:
        return _basilisk_ic.notify_raw(  # type: ignore
            canister_id, method, args_raw, payment
        )

    @staticmethod
    def performance_counter(counter_type: nat32) -> nat64:
        return _basilisk_ic.performance_counter(counter_type)  # type: ignore

    @staticmethod
    def print(*args: Any):
        string_list = [str(arg) for arg in args]
        _basilisk_ic.print(" ".join(string_list))  # type: ignore

    @staticmethod
    def reject(x: str):
        _basilisk_ic.reject(x)  # type: ignore

    @staticmethod
    def reject_code() -> RejectionCode:
        return _basilisk_ic.reject_code()  # type: ignore

    @staticmethod
    def reject_message() -> str:
        return _basilisk_ic.reject_message()  # type: ignore

    @staticmethod
    def reply(value: Any):
        first_called_function_name = get_first_called_function_name()
        (_basilisk_ic.reply(first_called_function_name, value))  # type: ignore

    @staticmethod
    def reply_raw(x: Any):
        _basilisk_ic.reply_raw(x)  # type: ignore

    @staticmethod
    def set_certified_data(data: blob):
        _basilisk_ic.set_certified_data(data)  # type: ignore

    @staticmethod
    def set_timer(delay: Duration, func: Callable[[], Any]) -> TimerId:
        return _basilisk_ic.set_timer(delay, func)  # type: ignore

    @staticmethod
    def set_timer_interval(interval: Duration, func: Callable[[], Any]) -> TimerId:
        return _basilisk_ic.set_timer_interval(interval, func)  # type: ignore

    @staticmethod
    def stable_bytes() -> blob:
        return _basilisk_ic.stable_bytes()  # type: ignore

    @staticmethod
    def stable_grow(new_pages: nat32) -> StableGrowResult:
        return _basilisk_ic.stable_grow(new_pages)  # type: ignore

    @staticmethod
    def stable_read(offset: nat32, length: nat32) -> blob:
        return _basilisk_ic.stable_read(offset, length)  # type: ignore

    @staticmethod
    def stable_size() -> nat32:
        return _basilisk_ic.stable_size()  # type: ignore

    @staticmethod
    def stable_write(offset: nat32, buf: blob):
        _basilisk_ic.stable_write(offset, buf)  # type: ignore

    @staticmethod
    def stable64_grow(new_pages: nat64) -> Stable64GrowResult:
        return _basilisk_ic.stable64_grow(new_pages)  # type: ignore

    @staticmethod
    def stable64_read(offset: nat64, length: nat64) -> blob:
        return _basilisk_ic.stable64_read(offset, length)  # type: ignore

    @staticmethod
    def stable64_size() -> nat64:
        return _basilisk_ic.stable64_size()  # type: ignore

    @staticmethod
    def stable64_write(offset: nat64, buf: blob):
        _basilisk_ic.stable64_write(offset, buf)  # type: ignore

    @staticmethod
    def time() -> nat64:
        return _basilisk_ic.time()  # type: ignore

    @staticmethod
    def trap(message: str) -> NoReturn:  # type: ignore
        _basilisk_ic.trap(message)  # type: ignore


class Service:
    canister_id: Principal

    def __init__(self, canister_id: Principal):
        self.canister_id = canister_id


P = ParamSpec("P")


class AsyncInfo:
    name: str
    args: list[Any]

    def __init__(self, name: str, args: list[Any]):
        self.name = name
        self.args = args

    def with_cycles(self, cycles: nat64) -> "AsyncInfo":
        return AsyncInfo("call_with_payment", [*self.args, cycles])

    def with_cycles128(self, cycles: nat) -> "AsyncInfo":
        return AsyncInfo("call_with_payment128", [*self.args, cycles])

    def notify(self) -> NotifyResult:
        qualname: str = self.args[1]
        with_payment = (
            "with_payment128_"
            if self.name == "call_with_payment" or self.name == "call_with_payment128"
            else ""
        )
        notify_function_name = (
            f'notify_{with_payment}{qualname.replace(".", "_")}_wrapper'
        )

        return getattr(_basilisk_ic, notify_function_name)(self.args)  # type: ignore


def service_method(func: Callable[P, T]) -> Callable[P, CallResult[T]]:
    def intermediate_func(*args):  # type: ignore
        the_self = args[0]  # type: ignore
        selfless_args = args[1:]  # type: ignore

        return AsyncInfo(
            "call",
            [the_self.canister_id, func.__qualname__, *selfless_args],  # type: ignore
        )

    return intermediate_func  # type: ignore


def service_query(func: Callable[P, T]) -> Callable[P, CallResult[T]]:
    return service_method(func)


def service_update(func: Callable[P, T]) -> Callable[P, CallResult[T]]:
    return service_method(func)


K = TypeVar("K")
V = TypeVar("V")


class KeyTooLarge(Record):
    given: nat32
    max: nat32


class ValueTooLarge(Record):
    given: nat32
    max: nat32


class StableBTreeMap(Generic[K, V]):
    """A map based on a self-balancing tree that persists across canister upgrades."""

    def __init__(self, memory_id: nat8, max_key_size: int, max_value_size: int):
        self.memory_id = memory_id

    def contains_key(self, key: K) -> bool:
        return _basilisk_ic.stable_b_tree_map_contains_key(self.memory_id, key)  # type: ignore

    def get(self, key: K) -> Opt[V]:
        return _basilisk_ic.stable_b_tree_map_get(self.memory_id, key)  # type: ignore

    def insert(self, key: K, value: V) -> Opt[V]:
        return _basilisk_ic.stable_b_tree_map_insert(self.memory_id, key, value)  # type: ignore

    def is_empty(self) -> bool:
        return _basilisk_ic.stable_b_tree_map_is_empty(self.memory_id)  # type: ignore

    def items(self) -> Vec[Tuple[K, V]]:
        return _basilisk_ic.stable_b_tree_map_items(self.memory_id)  # type: ignore

    def keys(self) -> Vec[K]:
        return _basilisk_ic.stable_b_tree_map_keys(self.memory_id)  # type: ignore

    def len(self) -> nat64:
        return _basilisk_ic.stable_b_tree_map_len(self.memory_id)  # type: ignore

    def remove(self, key: K) -> Opt[V]:
        return _basilisk_ic.stable_b_tree_map_remove(self.memory_id, key)  # type: ignore

    def values(self) -> Vec[V]:
        return _basilisk_ic.stable_b_tree_map_values(self.memory_id)  # type: ignore


def match(
    variant: Union[TypedDict, object], matcher: dict[str, Callable[[Any], T]]
) -> T:
    if isinstance(variant, dict):
        for key, value in matcher.items():
            if key in variant:
                return value(variant[key])

            if key == "_":
                return value(None)
    else:
        err_value = getattr(variant, "Err", None)

        if err_value is not None:
            return matcher["Err"](err_value)

        return matcher["Ok"](getattr(variant, "Ok"))

    raise Exception("No matching case found")


# Exceptions
class Error(Exception):
    """Base exception for all errors raised by Basilisk"""

    pass


class CandidError(Error):
    """Raised when converting to/from Candid values."""

    pass
