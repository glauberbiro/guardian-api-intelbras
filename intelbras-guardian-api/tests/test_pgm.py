"""PGM (programmable output) control for ISECNet V1 panels (ANM 24 NET / AMT 2018)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.isecnet_protocol import ISECNetProtocol


# Live ANM 24 NET captures (44 data bytes). data[38] is the output byte:
# bit 6 = PGM1, bit 5 = PGM2.
ANM24_ARMED_PGM1_ON = bytes.fromhex(
    "e900000000000000000000000000000000000024660103001256041126"
    "000000000000000000400000000000"
)
ANM24_DISARMED_PGM_OFF = bytes.fromhex(
    "e902000000000000000000000000000000000024660100001323041126"
    "000000000000000000000000000000"
)


def _wrap_v1(data: bytes) -> bytes:
    packet = bytes([len(data)]) + data
    checksum = 0
    for b in packet:
        checksum ^= b
    return packet + bytes([checksum ^ 0xFF])


def test_pgm_on_frame_matches_isecmobile_doc():
    # [size][0xE9][!][pwd][0x50][L][0x31][!][checksum]
    cmd = ISECNetProtocol()._build_isecv1_pgm_cmd("1234", 1, True)
    assert cmd.hex() == "0ae92131323334504c312135"


def test_pgm_off_frame_matches_isecmobile_doc():
    cmd = ISECNetProtocol()._build_isecv1_pgm_cmd("1234", 1, False)
    assert cmd.hex() == "0ae92131323334504431213d"


def test_pgm_address_mapping():
    proto = ISECNetProtocol()
    assert proto._build_isecv1_pgm_cmd("1234", 2, True)[-3] == 0x32
    assert proto._build_isecv1_pgm_cmd("1234", 19, True)[-3] == 0x43
    with pytest.raises(ValueError):
        proto._build_isecv1_pgm_cmd("1234", 0, True)
    with pytest.raises(ValueError):
        proto._build_isecv1_pgm_cmd("1234", 20, True)


def test_pgm_states_parsed_from_output_byte():
    proto = ISECNetProtocol()
    armed = proto._parse_isecv1_status_response(_wrap_v1(ANM24_ARMED_PGM1_ON))
    assert armed.pgm_states == {1: True, 2: False}

    disarmed = proto._parse_isecv1_status_response(_wrap_v1(ANM24_DISARMED_PGM_OFF))
    assert disarmed.pgm_states == {1: False, 2: False}
