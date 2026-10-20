# Modified for Seabed Sidescan on 2026-10-19: metadata follows explicitly
# selected XTF channels; missing channel headers fail. See ../../THIRD_PARTY.md.
# Modified on 2026-10-20: require matched, ordered JSF port/starboard pings.
import numpy as np
from sidescantools.xtf_wrapper import XTFWrapper
import pyxtf
from sidescantools.jsf import JSFFile, JSFSystemInformation, JSFSonarDataPacket
import os
from pathlib import Path
from datetime import datetime


class SidescanFile:
    """Wrapper to read sidescan files.
    Format definition: https://www.exail.com/media-file/9742/xtf-file-format-specification-rev42.pdf
    """

    filepath: Path
    """Path to read file"""
    choose_subsys: int
    """Use this argument if u are reading a JSF File that contains multiple subsystems 
        to choose the sub system which shall be evaluated:

        - 0: First sub system (usually LF if present, otherwise HF)
        - 1: Second sub system (usually HF if LF and HF are present)
        - 2: Custom/additional sub systems
    """
    ping_len: int
    """Length of a ping in sample number"""
    num_ping: int
    """Length of a ping in sample number"""
    num_ch: int
    """Number of channels"""
    subsys_num: int
    """Number of Subsystems"""
    data: np.ndarray
    """raw sidescan data - [channel index, ping index, sample index]"""
    subsys_names: list
    """Names of subsystem (in case of JSF)"""
    sound_velocity: float
    """SOS/2 in water"""
    ping_x_axis: np.ndarray
    """X-Axis in m for a single ping (slant direction)"""
    timestamp: list
    """Time of each ping"""
    starting_depth: np.ndarray
    """Starting Depth (window offset) in Samples"""
    longitude: np.ndarray
    """Longitude in degree
    """
    latitude: np.ndarray
    """Latitude in degree
    """
    coord_units: int
    gain_adc: np.ndarray
    """Gain Factor of ADC"""
    depth: np.ndarray
    """Depth in Meters (Below Water Surface)"""
    packet_no: np.ndarray
    """Packet Number"""
    sensor_heading: np.ndarray
    """Sensor heading in degrees"""
    sensor_pitch: np.ndarray
    """Pitch in degrees (positive=nose up)"""
    sensor_primary_altitude: np.ndarray
    """Distance from towfish to the sea floor"""
    sensor_roll: np.ndarray
    """Roll in degrees (positive=roll to starboard)"""
    sensor_speed: np.ndarray
    """Speed of towfish in knots"""
    sensor_aux_altitude: np.ndarray
    """Auxiliary altitude"""

    seconds_per_ping: np.ndarray
    """in s per channel"""
    slant_range: np.ndarray
    """in m per channel"""

    def __init__(self, filepath: str | os.PathLike, choose_subsys=0):
        self.filepath = Path(filepath)
        self.choose_subsys = choose_subsys

        # check whether this is XTF/JSF/not supported
        if self.filepath.suffix.casefold() == ".xtf":
            xtf = XTFWrapper(file_path=self.filepath)

            # set data fields
            self.ping_len = xtf.num_sample_per_ping
            self.num_ch = xtf.num_ch
            self.channel_indices = xtf.channel_indices
            self.data = xtf.sonar_data
            self.num_ping = np.shape(xtf.sonar_data)[-2]

            self.sound_velocity = np.empty(self.num_ping)
            self.timestamp = [datetime] * self.num_ping
            self.sensor_heading = np.empty(self.num_ping)
            self.sensor_pitch = np.empty(self.num_ping)
            self.sensor_aux_altitude = np.empty(self.num_ping)
            self.sensor_primary_altitude = np.empty(self.num_ping)
            self.sensor_roll = np.empty(self.num_ping)
            self.sensor_speed = np.empty(self.num_ping)
            self.longitude = np.empty(self.num_ping)
            self.latitude = np.empty(self.num_ping)
            self.depth = np.empty(self.num_ping)
            self.packet_no = np.empty(self.num_ping)
            self.seconds_per_ping = np.empty((self.num_ch, self.num_ping))
            self.slant_range = np.empty((self.num_ch, self.num_ping))

            # not included
            self.starting_depth = np.zeros(self.num_ping)
            self.gain_adc = np.zeros(self.num_ping)

            # read XTF info
            for p_idx in range(self.num_ping):
                self.sound_velocity[p_idx] = (
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].SoundVelocity * 2
                )  # half SOS in water
                self.timestamp[p_idx] = datetime(
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].Year,
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].Month,
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].Day,
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].Hour,
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].Minute,
                    xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx].Second,
                )
                self.sensor_heading[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorHeading
                self.sensor_pitch[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorPitch
                self.sensor_primary_altitude[p_idx] = xtf.packets[
                    pyxtf.XTFHeaderType.sonar
                ][p_idx].SensorPrimaryAltitude
                self.sensor_roll[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorRoll
                self.sensor_speed[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorSpeed
                self.sensor_aux_altitude[p_idx] = xtf.packets[
                    pyxtf.XTFHeaderType.sonar
                ][p_idx].SensorAuxAltitude
                self.longitude[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorXcoordinate
                self.latitude[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorYcoordinate
                self.depth[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].SensorDepth
                self.packet_no[p_idx] = xtf.packets[pyxtf.XTFHeaderType.sonar][
                    p_idx
                ].PingNumber
                for ch_idx in range(self.num_ch):
                    header_ch_idx = (
                        xtf.channel_indices[ch_idx]
                        if hasattr(xtf, "channel_indices")
                        else ch_idx
                    )
                    if (
                        len(
                            xtf.packets[pyxtf.XTFHeaderType.sonar][
                                p_idx
                            ].ping_chan_headers
                        )
                        > header_ch_idx
                    ):
                        self.seconds_per_ping[ch_idx, p_idx] = (
                            xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx]
                            .ping_chan_headers[header_ch_idx]
                            .SecondsPerPing
                        )
                        self.slant_range[ch_idx, p_idx] = (
                            xtf.packets[pyxtf.XTFHeaderType.sonar][p_idx]
                            .ping_chan_headers[header_ch_idx]
                            .SlantRange
                        )
                    else:
                        raise ValueError(f"Missing XTF channel {header_ch_idx} header in ping {p_idx}")

            self.ping_x_axis = xtf.x_axis_m

        elif self.filepath.suffix.casefold() == ".jsf":
            jsf_file = JSFFile(self.filepath)

            # find number and names of subsystems in the present data
            self.subsys_names = []
            self.subsys_num = 0
            self.num_ch = 0
            for packet in jsf_file.packets:
                if type(packet) == JSFSystemInformation:
                    self.subsys_num = packet.num_subsystems
                if type(packet) == JSFSonarDataPacket:
                    if packet.header.subsys_no not in self.subsys_names:
                        self.subsys_names.append(packet.header.subsys_no)

            if len(self.subsys_names) != self.subsys_num:
                print(
                    f"Mismatch on subsys names: {self.subsys_names} and expected num: {self.subsys_num}"
                )
                self.subsys_num = len(self.subsys_names)

            data_port = []
            data_star = []
            ping_ids = [[], []]
            samples_per_ping = None

            for packet in jsf_file.packets:
                if type(packet) == JSFSonarDataPacket:

                    # dual channel data of desired sub system
                    if packet.header.subsys_no == self.subsys_names[self.choose_subsys]:
                        channel = packet.header.channel
                        if channel not in (0, 1):
                            raise ValueError(
                                f"Unsupported JSF channel {channel}; only port channel 0 and starboard channel 1 are supported."
                            )
                        ids = ping_ids[channel]
                        ping_id = packet.message.ping_no
                        if ids and ping_id <= ids[-1]:
                            raise ValueError(
                                f"JSF channel {channel} ping IDs must increase strictly; duplicate, split or out-of-order ping {ping_id}."
                            )
                        ids.append(ping_id)
                        samples = np.asarray(packet.message.data)
                        if (samples.ndim != 1 or samples.size == 0
                                or samples.size != packet.message.samples
                                or not np.isfinite(samples).all()
                                or (samples_per_ping is not None and samples.size != samples_per_ping)):
                            raise ValueError(
                                f"JSF ping {ping_id}, channel {channel} has invalid or incompatible samples; "
                                "both channels must have the same nonempty sample count for every ping."
                            )
                        samples_per_ping = samples.size

                        # portside
                        if packet.header.channel == 0:
                            data_port.append(packet.message.data)

                        # starboard
                        elif packet.header.channel == 1:
                            data_star.append(packet.message.data)

            # Never pair rows merely because the arrays happen to have equal lengths.
            # Shared gaps are permitted, but each port ping needs its matching starboard ping.
            if not ping_ids[0] or ping_ids[0] != ping_ids[1]:
                raise ValueError("JSF port/starboard ping IDs must match one-to-one in chronological order.")
            self.num_ch = 2

            # Merge the data
            self.data = np.array((np.fliplr(data_port), data_star))

            # set data fields
            self.ping_len = self.data.shape[-1]
            self.num_ping = self.data.shape[-2]

            self.sound_velocity = np.empty(self.num_ping)
            self.timestamp = [datetime] * self.num_ping
            self.sensor_heading = np.empty(self.num_ping)
            self.sensor_pitch = np.empty(self.num_ping)
            self.sensor_primary_altitude = np.empty(self.num_ping)
            self.sensor_roll = np.empty(self.num_ping)
            self.sensor_speed = np.empty(self.num_ping)
            self.longitude = np.empty(self.num_ping)
            self.latitude = np.empty(self.num_ping)
            self.depth = np.empty(self.num_ping)
            self.packet_no = np.empty(self.num_ping)
            self.seconds_per_ping = np.empty((self.num_ch, self.num_ping))
            self.slant_range = np.empty((self.num_ch, self.num_ping))

            # not included
            self.sensor_aux_altitude = np.zeros(self.num_ping)

            self.starting_depth = np.zeros(self.num_ping)
            self.gain_adc = np.zeros(self.num_ping)

            # walk through all packets and take meta info from channel 0
            p_idx = 0

            # Interpret sonar data packets
            for packet in jsf_file.packets:
                if type(packet) == JSFSonarDataPacket:
                    if (
                        packet.header.subsys_no == self.subsys_names[self.choose_subsys]
                        and packet.header.channel == 0
                    ):

                        self.sound_velocity[p_idx] = packet.message.SOS
                        self.timestamp[p_idx] = datetime.fromtimestamp(
                            packet.message.time
                        )
                        self.sensor_heading[p_idx] = (
                            packet.message.compass_heading / 100
                        )
                        self.sensor_pitch[p_idx] = packet.message.pitch / 32768 * 180
                        self.sensor_primary_altitude[p_idx] = (
                            packet.message.altitude / 1e3
                        )
                        self.sensor_roll[p_idx] = packet.message.roll / 32768 * 180
                        self.sensor_speed[p_idx] = packet.message.speed / 10 / 1.944

                        self.depth[p_idx] = packet.message.depth / 1e3
                        self.packet_no[p_idx] = packet.message.packet_no
                        self.seconds_per_ping[:, p_idx] = (
                            packet.message.sampling_interval_ns / 1e9
                        )
                        # check whether SOS is valid
                        sos = packet.message.SOS
                        if sos == 0:
                            sos = 1500
                        # round to 2 decimals here to avoid potential resampling of data in slant range correction
                        self.slant_range[:, p_idx] = np.round(
                            self.seconds_per_ping[0, p_idx] * self.ping_len * sos / 2,
                            decimals=2,
                        )
                        self.starting_depth[p_idx] = packet.message.starting_depth
                        self.gain_adc[p_idx] = packet.message.gain_adc

                        if packet.message.coord_units == 2:
                            # convert Latitude, longitude in minutes of arc times 10000 to degree
                            self.longitude[p_idx] = (
                                packet.message.longitude / 10000 / 60
                            )
                            self.latitude[p_idx] = packet.message.latitude / 10000 / 60
                        else:
                            # TODO: implement other cases:
                            # 1 = X, Y in millimeters
                            # 2 = Latitude, longitude in minutes of arc times 10000
                            # 3 = X, Y in decimeters
                            # 4 = X, Y in centimeters
                            raise NotImplementedError

                        p_idx += 1

            self.ping_x_axis = np.linspace(0, self.slant_range[0][0], self.ping_len)

        else:
            print(f"File type {self.filepath.suffix.casefold()} isn't supported.")
            raise NotImplementedError
