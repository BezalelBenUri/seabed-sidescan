"""Safety regressions for the optional backend without installing GMT/Qt."""
import ast
import math
import os
import runpy
import shutil
import struct
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from scipy import interpolate
from scipy.signal import savgol_filter

BACKEND = Path(__file__).resolve().parents[1] / "vendor/sidescantools-main/src/sidescantools"
if not BACKEND.is_dir():
    pytest.skip("Optional vendor source is not included in the core source distribution.", allow_module_level=True)


def wrapper_class(pings, channels=4, decoder=None, roles=None):
    header = SimpleNamespace(NumberOfSonarChannels=channels, NavUnits=3,
                             ChanInfo=[SimpleNamespace(TypeOfChannel=role)
                                       for role in (roles or [1, 2, 1, 2])])
    if decoder is None:
        def decoder(records, **kwargs):
            return np.vstack([p.data[kwargs["channel"]] for p in records[::-1]])
    fake = SimpleNamespace(XTFFileHeader=lambda: header,
                           xtf_read=lambda path: (header, {0: pings}),
                           XTFHeaderType=SimpleNamespace(sonar=0), concatenate_channel=decoder)
    with patch.dict("sys.modules", {"pyxtf": fake}):
        return runpy.run_path(str(BACKEND / "xtf_wrapper.py"))["XTFWrapper"]


def ping(value=1):
    return SimpleNamespace(data=[np.array([value, value + 1])] * 4,
                           ping_chan_headers=[SimpleNamespace(NumSamples=2, SlantRange=40,
                                                              ChannelNumber=channel)
                                              for channel in range(4)])


@pytest.mark.parametrize("pair", ["bad", "0", "0,0", "1,8", "-1,1", "0,1,2"])
def test_xtf_never_silently_changes_channel_selection(monkeypatch, pair):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", pair)
    with pytest.raises(ValueError, match="channel"):
        wrapper_class([ping()])(Path("fixture.xtf"))


def test_xtf_one_ping_and_sample_metadata_alignment(monkeypatch):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", "2,3")
    decoded = wrapper_class([ping(7)])(Path("fixture.xtf"))
    assert decoded.channel_indices == [2, 3]
    np.testing.assert_equal(decoded.sonar_data[0], [[7, 8]])
    np.testing.assert_equal(decoded.x_axis_m, [0, 40])
    decoded = wrapper_class([ping(7), ping(9)])(Path("fixture.xtf"))
    np.testing.assert_equal(decoded.sonar_data[0], [[7, 8], [9, 10]])


def test_xtf_missing_samples_and_decoder_failures_are_errors(monkeypatch):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", "0,1")
    broken = ping()
    broken.data = [np.array([])] * 4
    with pytest.raises(ValueError, match="Missing or invalid"):
        wrapper_class([ping(), broken])(Path("fixture.xtf"))
    def fail(*args, **kwargs):
        raise RuntimeError("decoder failed")
    with pytest.raises(ValueError, match="Cannot decode"):
        wrapper_class([ping()], decoder=fail)(Path("fixture.xtf"))


@pytest.mark.parametrize("pair", ["1,0", "0,2", "1,3", "3,2"])
def test_xtf_rejects_reversed_and_same_side_channel_pairs(monkeypatch, pair):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", pair)
    with pytest.raises(ValueError, match="port.*starboard"):
        wrapper_class([ping()])(Path("fixture.xtf"))


@pytest.mark.parametrize("channel_number", [None, -1, 8])
def test_xtf_requires_valid_file_header_channel_mapping(monkeypatch, channel_number):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", "0,1")
    record = ping()
    record.ping_chan_headers[0].ChannelNumber = channel_number
    with pytest.raises(ValueError, match="channel mapping"):
        wrapper_class([record])(Path("fixture.xtf"))


@pytest.mark.parametrize("role", [0, 3, 255])
def test_xtf_rejects_unknown_or_non_sidescan_channel_roles(monkeypatch, role):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", "0,1")
    with pytest.raises(ValueError, match="port.*starboard"):
        wrapper_class([ping()], roles=[role, 2, 1, 2])(Path("fixture.xtf"))


def test_xtf_resolves_roles_through_ping_channel_number(monkeypatch):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", "0,1")
    record = ping()
    record.ping_chan_headers[0].ChannelNumber = 1
    record.ping_chan_headers[1].ChannelNumber = 0
    result = wrapper_class([record], roles=[2, 1, 1, 2])(Path("fixture.xtf"))
    assert result.channel_indices == [0, 1]


def test_xtf_rejects_channel_identity_changes_between_pings(monkeypatch):
    monkeypatch.setenv("SIDESCANTOOLS_XTF_CHANNEL_PAIR", "0,1")
    second = ping()
    second.ping_chan_headers[0].ChannelNumber = 2  # Another port channel is still a different channel.
    with pytest.raises(ValueError, match="channel mapping"):
        wrapper_class([ping(), second])(Path("fixture.xtf"))


def jsf_message_class():
    return runpy.run_path(str(BACKEND / "jsf.py"))["JSFSonarDataMessage"]


def jsf_message_header(cls, data_format=0, samples=3, weighting=1):
    values = {name: b"" if fmt.endswith("s") else 0
              for name, fmt in cls.format_def.items()}
    values.update(data_format=data_format, samples=samples, weighting=weighting)
    return struct.pack("=" + "".join(cls.format_def.values()), *values.values())


@pytest.mark.parametrize("data_format", [1, 2, 9, 256])
def test_jsf_rejects_uninterpreted_sample_formats_before_payload_read(data_format):
    cls = jsf_message_class()
    with pytest.raises(NotImplementedError, match=f"JSF.*{data_format}.*envelope"):
        cls(jsf_message_header(cls, data_format=data_format))


@pytest.mark.parametrize("data_format", [1, 2, 9, 256])
def test_jsf_rejects_uninterpreted_sample_formats_on_direct_load(data_format):
    cls = jsf_message_class()
    message = cls.__new__(cls)
    message.data_format, message.samples, message.weighting = data_format, 3, 1
    payload = struct.pack("6h" if data_format in (1, 9) else "3h",
                          *range(6 if data_format in (1, 9) else 3))
    with pytest.raises(NotImplementedError, match=f"JSF.*{data_format}.*envelope"):
        message.load_data(payload)


def test_jsf_envelope_conversion_retains_exact_existing_numerics():
    cls = jsf_message_class()
    message = cls(jsf_message_header(cls))
    message.load_data(struct.pack("3h", -4, 0, 300))
    assert message.byte_len_sonar_data == 6
    assert message.data.dtype == np.float32
    np.testing.assert_equal(message.data, [-2, 0, 150])


def jsf_sidescan(ping_ids, sample_counts=None, extra_channel=None, invalid_sample=False):
    class SonarPacket:
        pass
    class SystemInformation:
        pass
    packets = []
    for channel, ids in enumerate(ping_ids):
        for index, ping_id in enumerate(ids):
            count = sample_counts[channel][index] if sample_counts else 3
            data = np.arange(count, dtype=np.float32) + 1 + channel * 10 + index * 100
            if invalid_sample:
                data[0] = np.nan
            packet = SonarPacket()
            packet.header = SimpleNamespace(subsys_no=20, channel=channel)
            packet.message = SimpleNamespace(
                ping_no=ping_id, data=data, samples=count, SOS=1500, time=1700000000 + ping_id,
                compass_heading=0, pitch=0, altitude=1000, roll=0, speed=0, depth=1000,
                packet_no=1, sampling_interval_ns=1000000, starting_depth=0, gain_adc=1,
                coord_units=2, longitude=6 * 600000, latitude=5 * 600000)
            packets.append(packet)
    if extra_channel is not None:
        packet = SonarPacket()
        packet.header = SimpleNamespace(subsys_no=20, channel=extra_channel)
        packet.message = SimpleNamespace(ping_no=10, data=np.ones(3), samples=3)
        packets.append(packet)
    tree = ast.parse((BACKEND / "sidescan_file.py").read_text(encoding="utf-8-sig"))
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    globals_ = {"np": np, "Path": Path, "os": os, "datetime": datetime,
                "JSFFile": lambda path: SimpleNamespace(packets=packets),
                "JSFSonarDataPacket": SonarPacket, "JSFSystemInformation": SystemInformation}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "sidescan_file.py", "exec"), globals_)
    return globals_["SidescanFile"](Path("fixture.jsf"))


@pytest.mark.parametrize("ping_ids", [([10, 11], [11, 12]), ([10, 11], [10]),
                                    ([10, 10], [10, 10]), ([11, 10], [11, 10])])
def test_jsf_rejects_unpaired_duplicate_or_nonchronological_pings(ping_ids):
    with pytest.raises(ValueError, match="JSF.*ping"):
        jsf_sidescan(ping_ids)


@pytest.mark.parametrize("sample_counts", [([3, 3], [4, 4]), ([3, 4], [3, 4])])
def test_jsf_rejects_incompatible_sample_shapes(sample_counts):
    with pytest.raises(ValueError, match="JSF.*sample"):
        jsf_sidescan(([10, 11], [10, 11]), sample_counts=sample_counts)


def test_jsf_rejects_nonfinite_samples():
    with pytest.raises(ValueError, match="JSF.*sample"):
        jsf_sidescan(([10], [10]), invalid_sample=True)


def test_jsf_rejects_unsupported_channel_with_useful_error():
    with pytest.raises(ValueError, match="JSF.*channel"):
        jsf_sidescan(([10], [10]), extra_channel=2)


def test_jsf_matched_nonsuccessive_ping_ids_keep_sample_and_navigation_order():
    result = jsf_sidescan(([10, 12], [10, 12]))
    np.testing.assert_equal(result.data[0], [[3, 2, 1], [103, 102, 101]])
    np.testing.assert_equal(result.data[1], [[11, 12, 13], [111, 112, 113]])
    np.testing.assert_equal(result.longitude, [6, 6])
    assert result.timestamp == [datetime.fromtimestamp(1700000010), datetime.fromtimestamp(1700000012)]


def georeferencer_class():
    # Load the actual class with deterministic geographic fakes. Optional native
    # dependency imports are excluded; tested methods remain the shipped code.
    tree = ast.parse((BACKEND / "georef_thread.py").read_text(encoding="utf-8-sig"))
    class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    globals_ = {"np": np, "Path": Path, "os": os, "math": math, "SidescanFile": object,
                "savgol_filter": savgol_filter, "interpolate": interpolate}
    globals_["utm"] = SimpleNamespace(
        from_latlon=lambda lat, lon: (lon * 1000, lat * 1000, 31, "N" if lat >= 0 else "M"),
        to_latlon=lambda east, north, zone, letter: (north / 1000, east / 1000),
        OutOfRangeError=ValueError,
    )
    globals_["CRS"] = SimpleNamespace(from_dict=lambda params: SimpleNamespace(
        to_authority=lambda: ("EPSG", "32731" if params["south"] else "32631")))
    exec(compile(ast.Module(body=[class_node], type_ignores=[]), "georef_thread.py", "exec"), globals_)
    return globals_["Georeferencer"]


def test_georeference_failure_and_short_lines_are_not_success():
    cls = georeferencer_class()
    instance = cls.__new__(cls)
    instance.PING = [1] * 300
    with pytest.raises(ValueError, match="more than 300"):
        instance.process()
    instance.PING = [1] * 301
    instance.prep_data = lambda: None
    instance.channel_stack = lambda: np.ones(301)
    def fail(**kwargs):
        raise RuntimeError("GMT failure")
    instance.georeference = fail
    with pytest.raises(RuntimeError, match="GMT failure"):
        instance.process()


def test_navigation_accepts_greenwich_but_rejects_invalid_fixes():
    cls = georeferencer_class()
    instance = cls.__new__(cls)
    instance.sidescan_file = SimpleNamespace(longitude=[0, 0, np.nan, 181, 5], latitude=[5, 0, 5, 5, 85])
    np.testing.assert_equal(instance.navigation_mask(), [True, False, False, False, False])


@pytest.mark.parametrize("lat,crs", [(5, "EPSG:32631"), (-5, "EPSG:32731")])
def test_ground_distance_uses_degrees_and_correct_utm_hemisphere(lat, crs):
    cls = georeferencer_class()
    instance = cls.__new__(cls)
    instance.channel = 0
    instance.PING = np.arange(301)
    instance.active_proc_data = True
    instance.proc_data = np.ones((301, 2))
    instance.vertical_beam_angle = 60
    instance.cable_out = instance.x_offset = instance.y_offset = 0
    instance.sidescan_file = SimpleNamespace(
        longitude=np.linspace(1, 1.3, 301), latitude=np.full(301, lat, dtype=float),
        sensor_heading=np.full(301, 90), slant_range=np.full((2, 301), 100))
    instance.prep_data()
    assert instance.epsg_code == crs
    # East-going port swath lies north of the track, 100*cos(60deg)=50 m away.
    offsets = np.asarray(instance.LALO_OUTER)[:, 0] * 1000 - lat * 1000
    np.testing.assert_allclose(offsets, 50, atol=1e-7)


def test_sonar_zero_intensity_is_rejected():
    cls = georeferencer_class()
    instance = cls.__new__(cls)
    instance.sidescan_file = SimpleNamespace(longitude=np.ones(301), latitude=np.ones(301))
    instance.active_proc_data = True
    instance.proc_data = np.zeros((301, 2))
    instance.channel = 0
    with pytest.raises(ValueError, match="zero-only"):
        instance.channel_stack()


@pytest.mark.parametrize("northward,expected", [(False, [-7, -4]), (True, [4, -7])])
def test_layback_and_ship_offsets_follow_course(northward, expected):
    cls = georeferencer_class()
    instance = cls.__new__(cls)
    instance.channel = 0
    instance.PING = np.arange(301)
    instance.active_proc_data = True
    instance.proc_data = np.ones((301, 2))
    instance.vertical_beam_angle = 60
    instance.cable_out = 10 * np.sqrt(2)
    instance.x_offset, instance.y_offset = 3, 4
    lon = np.full(301, 1.0) if northward else np.linspace(1, 1.3, 301)
    lat = np.linspace(5, 5.3, 301) if northward else np.full(301, 5.0)
    instance.sidescan_file = SimpleNamespace(longitude=lon, latitude=lat,
        sensor_heading=np.full(301, 90), slant_range=np.full((2, 301), 100))
    instance.prep_data()
    np.testing.assert_allclose((instance.LOLA_plt[0] - [1, 5]) * 1000, expected, atol=1e-7)


def test_repeated_navigation_fixes_retain_original_ping_positions():
    cls = georeferencer_class()
    instance = cls.__new__(cls)
    instance.channel = 0
    instance.PING = np.arange(301)
    instance.active_proc_data = True
    instance.proc_data = np.ones((301, 2))
    instance.vertical_beam_angle = 60
    instance.cable_out = instance.x_offset = instance.y_offset = 0
    instance.sidescan_file = SimpleNamespace(
        longitude=np.repeat([1., 1.1, 1.2, 1.3, 1.4], [50, 30, 120, 40, 61]),
        latitude=np.full(301, 5.), sensor_heading=np.full(301, 90),
        slant_range=np.full((2, 301), 100))
    observed = []
    def spline(x, y, **kwargs):
        observed.append(np.asarray(x))
        return interpolate.make_interp_spline(x, y, **kwargs)
    instance.prep_data.__globals__["interpolate"] = SimpleNamespace(
        UnivariateSpline=interpolate.UnivariateSpline, make_interp_spline=spline)
    instance.prep_data()
    assert observed
    np.testing.assert_equal(observed[0], [0, 50, 80, 200, 240, 300])


def main_class():
    tree = ast.parse((BACKEND / "main_cli.py").read_text(encoding="utf-8-sig"))
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    import json
    globals_ = {"Path": Path, "os": os, "np": np, "json": json,
                "timer": lambda: 0, "PLOTTING": False, "CFG": object}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "main_cli.py", "exec"), globals_)
    return globals_["SidescanToolsMain"], globals_


def test_no_db_no_gain_manifest_and_unrelated_outputs(tmp_path, monkeypatch):
    cls, globals_ = main_class()
    cfg = SimpleNamespace(
        main_proc_params=SimpleNamespace(active_pie_slice_filter=False, btm_refinement_search_range=0.06,
            active_bottom_line_refinement=False, active_btm_refinement_shift_by_offset=False,
            active_bottom_line_smoothing=False, additional_bottom_line_inset=0, nadir_angle=0,
            active_gain_normalization=False, active_convert_dB=False, active_hist_equalization=False,
            vertical_beam_angle=60, georef_dir=str(tmp_path)),
        slant_gain_params=SimpleNamespace(chunk_size=1000),
        georef_view_params=SimpleNamespace(active_automatic_resolution=False, active_utm=True,
            active_export_navigation=False, active_blockmedian=True, output_resolution=1,
            output_search_radius=2, cable_out=0, x_offset=0, y_offset=0),
        meta_infos=SimpleNamespace(working_dir=str(tmp_path)))
    file = SimpleNamespace(data=[np.ones((301, 4))] * 2, channel_indices=[2, 3])
    preproc = SimpleNamespace(sonar_data_proc=[np.ones((301, 4))] * 2,
        slant_range_correction=lambda **kwargs: None,
        portside_bottom_dist=np.ones(301), starboard_bottom_dist=np.ones(301))
    globals_["SidescanFile"] = lambda **kwargs: file
    globals_["SidescanPreprocessor"] = lambda **kwargs: preproc
    class Georef:
        def __init__(self, **kwargs):
            self.path = tmp_path / f"channel{kwargs['channel']}.tif"
        def process(self):
            self.path.touch()
            return self.path
        @staticmethod
        def write_img(path, *args):
            path.touch()
    globals_["Georeferencer"] = Georef
    processor = cls.__new__(cls)
    processor.cfg = cfg
    processor.active_georef = True
    processor.sidescan_files_path = [tmp_path / "fixture.XTF"]
    marker = tmp_path / "unrelated.xyz"
    marker.write_text("user data", encoding="utf8")
    target = tmp_path / "manifest.json"
    monkeypatch.setenv("SIDESCANTOOLS_RUN_MANIFEST", str(target))
    report = processor.process()
    assert report["inputs"][0]["outputs"] == [
        {"channel": 0, "input_channel": 2, "path": str((tmp_path / "channel0.tif").resolve())},
        {"channel": 1, "input_channel": 3, "path": str((tmp_path / "channel1.tif").resolve())}]
    assert target.is_file()
    assert marker.read_text() == "user data"
    target.unlink()
    def failing_georeference(self):
        if self.path.name == "channel1.tif":
            raise RuntimeError("second channel failed")
        self.path.touch()
        return self.path
    Georef.process = failing_georeference
    with pytest.raises(RuntimeError, match="second channel failed"):
        processor.process()
    assert not target.exists()
    assert marker.read_text() == "user data"


@pytest.mark.skipif(os.name != "nt", reason="PowerShell patch installation is Windows-specific")
def test_backend_patch_materialization_is_reproducible_and_idempotent(tmp_path):
    source = BACKEND.parents[1]
    target = tmp_path / "checkout"
    shutil.copytree(source, target)
    (target / "src/sidescantools/xtf_wrapper.py").write_text("# old wrapper", encoding="utf8")
    (target / "src/sidescantools/jsf.py").write_text("# old JSF reader", encoding="utf8")
    (target / "src/sidescantools/sidescan_file.py").write_text("# old file reader", encoding="utf8")
    script = source.parents[1] / "scripts/patch_sidescantools_klein_cli.ps1"
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
               "-SidescanToolsRepo", str(target)]
    for _ in range(2):
        subprocess.run(command, check=True, capture_output=True, text=True)
        for name in ("xtf_wrapper.py", "jsf.py", "sidescan_file.py"):
            assert (target / "src/sidescantools" / name).read_bytes() == (BACKEND / name).read_bytes()
