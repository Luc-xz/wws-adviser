"""SNTP 时钟偏移测量（零第三方依赖，stdlib socket）。

动机：本机时钟漂移会让"新鲜度 = 本地 now − 源时间戳"失真（5_DATA §8），
VPS 无 systemd-timesync 时尤甚。启动时测一次偏移；|offset| 超阈值记 warning
并在 /health/dependencies 暴露。云防火墙常拦 UDP 123 → 测量失败一律降级为
unknown，绝不影响服务启动（技术架构 §16.1 健康语义）。
"""

import asyncio
import socket
import struct
import time
from dataclasses import dataclass

_NTP_EPOCH_DELTA = 2208988800  # NTP 纪元(1900) → Unix 纪元(1970) 秒差


def build_sntp_request() -> bytes:
    """48 字节 SNTPv4 客户端请求：LI=0, VN=4, Mode=3（纯函数可单测）。"""
    return struct.pack("!B", 0x1B) + b"\x00" * 47


def _read_ntp_timestamp(data: bytes, offset: int) -> float:
    """NTP 64 位时间戳（秒+小数）→ Unix 秒。"""
    seconds: int
    fraction: int
    seconds, fraction = struct.unpack("!II", data[offset : offset + 8])
    return seconds - _NTP_EPOCH_DELTA + fraction / 2**32


def parse_sntp_offset(response: bytes, t0: float, t3: float) -> float:
    """NTP 四时间戳偏移 θ = ((t1−t0)+(t2−t3))/2（t1/t2 = 服务器收/发时刻）。

    纯函数（合成报文可单测）；响应不足 48 字节抛 ValueError。
    """
    if len(response) < 48:
        raise ValueError(f"SNTP 响应过短: {len(response)}B")
    t1 = _read_ntp_timestamp(response, 32)  # originate 后是 receive(32)/transmit(40)
    t2 = _read_ntp_timestamp(response, 40)
    return ((t1 - t0) + (t2 - t3)) / 2


def measure_clock_offset_sync(
    host: str, *, port: int = 123, timeout: float = 3.0
) -> float:
    """阻塞测量一次偏移。网络失败抛 OSError/TimeoutError，由调用方降级。"""
    request = build_sntp_request()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        t0 = time.time()
        sock.sendto(request, (host, port))
        data, _ = sock.recvfrom(1024)
        t3 = time.time()
    return parse_sntp_offset(data, t0, t3)


@dataclass(frozen=True)
class ClockSkewReport:
    """时钟偏移测量结果。offset_seconds=None 表示未启用或测量失败（unknown）。"""

    offset_seconds: float | None
    threshold_seconds: int

    @property
    def status(self) -> str:
        if self.offset_seconds is None:
            return "unknown"
        return "ok" if abs(self.offset_seconds) <= self.threshold_seconds else "skew"


async def measure_clock_skew(host: str, threshold_seconds: int) -> ClockSkewReport:
    """线程内测一次 SNTP 偏移并分类。host 为空 = 禁用；任何失败 → unknown。"""
    disabled = ClockSkewReport(offset_seconds=None, threshold_seconds=threshold_seconds)
    if not host:
        return disabled
    try:
        offset = await asyncio.to_thread(measure_clock_offset_sync, host, timeout=3.0)
    except Exception:  # noqa: BLE001 — UDP 被拦/超时是常态，unknown 即可
        return disabled
    return ClockSkewReport(
        offset_seconds=round(offset, 3), threshold_seconds=threshold_seconds
    )
