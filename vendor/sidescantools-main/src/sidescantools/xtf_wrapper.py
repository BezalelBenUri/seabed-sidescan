# Modified for Seabed Sidescan on 2026-10-19: explicit channel selection and
# fail-fast decoding; never synthesize missing pings. See ../../THIRD_PARTY.md.
# Modified on 2026-10-20: require stable, mapped port/starboard channel roles.
from dataclasses import dataclass, field
import os
from pathlib import Path

import numpy as np
import pyxtf


@dataclass
class XTFWrapper:
    file_path: Path
    file_header: object = field(default_factory=pyxtf.XTFFileHeader)
    packets: dict = field(default_factory=dict)
    num_ch: int = 2
    channel_indices: list = field(default_factory=list)
    sonar_data: list = field(default_factory=list)

    def __post_init__(self):
        self.file_header, self.packets = pyxtf.xtf_read(str(self.file_path))
        available_channels = self.file_header.NumberOfSonarChannels
        if self.file_header.NavUnits != 3:
            raise ValueError('XTF navigation must use geographic degrees (NavUnits=3).')
        channel_pair = os.environ.get('SIDESCANTOOLS_XTF_CHANNEL_PAIR', '0,1')
        try:
            self.channel_indices = [int(ch.strip()) for ch in channel_pair.split(',')]
        except ValueError as exc:
            raise ValueError('XTF channel pair must contain two distinct channel numbers.') from exc
        if (len(self.channel_indices) != 2 or len(set(self.channel_indices)) != 2
                or any(ch < 0 or ch >= available_channels for ch in self.channel_indices)):
            raise ValueError(
                f'Invalid XTF channel pair {channel_pair!r}; the file advertises '
                f'{available_channels} channels. Select two distinct existing channels.'
            )
        pings = self.packets.get(pyxtf.XTFHeaderType.sonar, [])
        if not pings:
            raise ValueError(f'No sonar pings found in {self.file_path}')
        channel_numbers = {}
        for ping_index, ping in enumerate(pings):
            for output_channel, channel in enumerate(self.channel_indices):
                if (channel >= len(ping.ping_chan_headers) or channel >= len(ping.data)
                        or np.asarray(ping.data[channel]).ndim != 1
                        or len(ping.data[channel]) == 0
                        or len(ping.data[channel]) != ping.ping_chan_headers[channel].NumSamples):
                    raise ValueError(f'Missing or invalid XTF ping {ping_index}, channel {channel}')
                # Selected indices address the decoded ping arrays. ChannelNumber
                # maps that position to ChanInfo; index parity does not imply side.
                number = getattr(ping.ping_chan_headers[channel], 'ChannelNumber', None)
                info = getattr(self.file_header, 'ChanInfo', ())
                if (not isinstance(number, int) or not 0 <= number < len(info)
                        or (channel in channel_numbers and channel_numbers[channel] != number)):
                    raise ValueError(
                        f'Unsupported XTF channel mapping in ping {ping_index}, channel {channel}: '
                        f'ChannelNumber={number!r}; mappings must be valid and stable across pings.'
                    )
                channel_numbers[channel] = number
                # XTF TypeOfChannel: 1 = port, 2 = starboard. Downstream processing
                # assigns those sides to output channels 0 and 1, respectively.
                expected_role = (1, 2)[output_channel]
                if getattr(info[number], 'TypeOfChannel', None) != expected_role:
                    raise ValueError(
                        f'XTF channel pair {channel_pair!r} must be ordered port then starboard '
                        f'(TypeOfChannel 1,2); ping {ping_index}, channel {channel} maps to '
                        f'TypeOfChannel={getattr(info[number], "TypeOfChannel", None)!r}.'
                    )
        self.num_ch = 2
        print(f'XTF advertises {available_channels} sonar channels; processing {self.channel_indices}')
        self.sonar_data = []
        for channel in self.channel_indices:
            try:
                # pyxtf returns reverse chronological rows and sorts pings in place;
                # restore chronological rows so samples and metadata remain aligned.
                data = np.flipud(pyxtf.concatenate_channel(
                    pings, file_header=self.file_header, channel=channel, weighted=False
                ))
            except Exception as exc:
                raise ValueError(f'Cannot decode XTF channel {channel}: {self.file_path}') from exc
            if data.ndim != 2 or data.shape[0] != len(pings) or not np.isfinite(data).all():
                raise ValueError(f'Invalid decoded XTF data for channel {channel}')
            self.sonar_data.append(data)
        if self.sonar_data[0].shape != self.sonar_data[1].shape:
            raise ValueError('Selected XTF channels have different ping/sample dimensions.')
        primary = self.channel_indices[0]
        self.num_sample_per_ping = self.sonar_data[0].shape[1]
        self.x_axis_m = np.linspace(
            0, pings[0].ping_chan_headers[primary].SlantRange, self.num_sample_per_ping
        )
