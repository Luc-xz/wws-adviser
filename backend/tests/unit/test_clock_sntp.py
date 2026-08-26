"""SNTP 时钟偏移测量纯函数测试（无网络；clock-skew 技术债落地）。"""

import struct

from wws_adviser.infrastructure.clock_sntp import (
    ClockSkewReport,
    build_sntp_request,
    parse_sntp_offset,
)

_NTP_DELTA = 2208988800  # 1900→1970 秒差


def _ntp_ts(unix_seconds: float) -> bytes:
    secs = int(unix_seconds) + _NTP_DELTA
    frac = int(round((unix_seconds % 1) * 2**32))
    return struct.pack("!II", secs, frac)


def test_request_structure() -> None:
    req = build_sntp_request()
    assert len(req) == 48
    assert req[0] == 0x1B  # LI=0, VN=4, Mode=3（客户端）


def test_parse_offset_four_timestamp_formula() -> None:
    # 服务器收 t1=t0+10、发 t2=t1+1；本机发出 t0=1000、收回 t3=1002
    # θ = ((1010−1000)+(1011−1002))/2 = 9.5 → 本机比标准钟慢 9.5s
    response = b"\x24" + b"\x00" * 31 + _ntp_ts(1010.0) + _ntp_ts(1011.0)
    offset = parse_sntp_offset(response, t0=1000.0, t3=1002.0)
    assert abs(offset - 9.5) < 1e-6


def test_parse_short_response_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse_sntp_offset(b"\x00" * 10, t0=0.0, t3=1.0)


def test_skew_status_classification() -> None:
    # unknown（未启用/测量失败）/ 阈值内 ok / 超阈值 skew（负偏移同样算超）
    assert ClockSkewReport(offset_seconds=None, threshold_seconds=5).status == "unknown"
    assert ClockSkewReport(offset_seconds=5.0, threshold_seconds=5).status == "ok"
    assert ClockSkewReport(offset_seconds=-5.001, threshold_seconds=5).status == "skew"
