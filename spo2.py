#           SPO2 Viewer
#   Written by Kevin Williams - 2022
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

import json
import math
import numba
import numpy as np
import logging
import statistics as stat
from scipy import signal

# local includes
from debug import debug_timer
from resource_path import resource_path

@numba.jit
def calc_rms(list_in):
    total = 0
    for i in list_in:
        total = total + (i ** 2)
    total = total / len(list_in)
    return math.sqrt(total)

class SPO2:
    def __init__(self, cal_file: str, max_readings: int = 80):

        self._r_value_history_max = 10
        self._samples_per_second: int = 0

        # peak detection parameters
        self.pk_prominence: int = 1
        self.pk_holdoff: int = 500
        
        # default calibration tables
        self._default_cal_r: list = [0.4, 0.85, 0.98, 1.1, 10]
        self._default_cal_spo2: list = [100, 97, 96, 95, 0]

        # calibration tables
        self._cal_r: list = self._default_cal_r
        self._cal_spo2: list = self._default_cal_spo2

        # qualified calibration file path
        self._cal_file_path = resource_path(cal_file)
        self._load_cal_file(self._cal_file_path)

        # initialize the data storage and result variables
        self._max_readings: int = max_readings
        self.reset()
    
    ### Properties and Setters
    @property
    def heart_rate_inst(self) -> float:
        return self._heart_rate_inst
    @property
    def rms_red(self) -> float:
        return self._rms_red
    @property
    def rms_ir(self) -> float:
        return self._rms_ir
    @property
    def r_inst(self) -> float:
        return self._r_value
    @property
    def r_average(self) -> float:
        return np.average(self._r_value_history)
    @property
    def spo2(self) -> float:
        return np.interp(self.r_average, self._cal_r, self._cal_spo2)
    @property
    def heart_rate(self) -> float:
        return self._heart_rate_inst
    @property
    def heart_rate_avg(self) -> float:
        return self._heart_rate_avg
    @property
    def max_readings(self) -> int:
        return self._max_readings
    @property
    def samples_per_second(self) -> int:
        return self._samples_per_second
    
    # accessors for graph data
    @property
    def history_ir(self) -> tuple:
        return tuple(self._raw_ir)
    @property
    def history_red(self) -> tuple:
        return tuple(self._raw_red)
    
    # accessors and setters for calibration table
    @property
    def cal_table_r(self) -> tuple:
        return tuple(self._cal_r)
    @cal_table_r.setter
    def cal_table_r(self, data: list) -> None:
        if not any(i < 0 for i in data):
            self._cal_r = data
        else:
            raise ValueError(f"R calibration values can't be negative. {data}")
    @property
    def cal_table_spo2(self) -> tuple:
        return tuple(self._cal_spo2)
    @cal_table_spo2.setter
    def cal_table_spo2(self, data: list) -> None:
        if not any(math.floor(i) not in range(0, 101) for i in data):
            self._cal_spo2 = data
        else:
            raise ValueError(f"All SPO2 values must be between 0-100. {data}")


    ### External Methods
    def add_data(self, data: tuple[float, float], time: float) -> bool:
        """
        Add a raw datapoint to the RED, IR, and Time tables. 
        Data tuple is defined as: tuple(red, ir). 
        Automatically updates R, SPO2, and heartrate at the end of a capture period.
        Returns True if the end of the capture period was reached.
        """

        self._raw_red[self._data_index] = data[0]
        self._raw_ir[self._data_index] = data[1]
        self._raw_time[self._data_index] = time
        self._data_index = (self._data_index + 1) % self._max_readings
        if self._data_index == 0:
            self._calc_r()
            self._heart_rate_inst, self._heart_rate_avg = self._calc_hr()
            self._calc_sps()
            return True
        return False

    def reset(self) -> None:
        """Resets all data storage values and calculation results."""
        self._peaks: list = []
        self._rms_red: float = 0.0
        self._rms_ir: float = 0.0
        self._r_value: float = 0.0
        self._heart_rate_inst: float = 0.0
        self._heart_rate_avg: float = 0.0
        self._r_value_history = [0] * self._r_value_history_max
        self._raw_red: np.ndarray = np.zeros(self._max_readings)
        self._raw_ir: np.ndarray = np.zeros(self._max_readings)
        self._raw_time: np.ndarray = np.zeros(self._max_readings)
        self._heart_rate_history: list = [0] * 3
        self._data_index = 0   
    
    def save_cal(self):
        self._save_cal_file(self._cal_file_path)

    ### Internal methods
    @numba.jit
    def _calc_r(self) -> None:
        """
        Update the instantaneous R value and channel RMS. 
        Stores to R value history.
        """

        red_mean = stat.mean(self._raw_red)
        ir_mean  = stat.mean(self._raw_ir)
        norm_red = []
        norm_ir  = []
        for i in self._raw_red:
            norm_red.append(i - red_mean)
        for i in self._raw_ir:
            norm_ir.append(i - ir_mean)
        self._rms_red = calc_rms(norm_red)
        self._rms_ir  = calc_rms(norm_ir)
        self._r_value = (self._rms_red / self._rms_ir)
        self._r_value_history.append(self._r_value)
        self._r_value_history.pop(0)
    
    def _calc_hr(self) -> tuple[int, int]:
        """
        Converts the average time between peaks to frequency.
        Returns tuple: (instantanious_rate, average_rate)
        """
        self._detect_peaks()
        times = []
        if len(self._peaks) > 1:
            for i, value in enumerate(self._peaks):
                if i:
                    last = self._raw_time[self._peaks[i - 1]]
                    times.append(self._raw_time[value] - last)
        if len(times):
            freq = (1 / (sum(times) / len(times)))
            rate = freq * 1000 * 60

            # update heart rate history
            self._heart_rate_history.append(rate)
            self._heart_rate_history.pop(0)

            # return instantainous rate and averaged rate
            rate = round(rate)
            avg = round(stat.mean(self._heart_rate_history))
            return rate, avg
        else:
            return 0, 0
    
    def _calc_sps(self):
        time_range = self._raw_time[-1] - self._raw_time[0]
        self._samples_per_second = math.floor((self._max_readings / time_range) * 1000)

    def _detect_peaks(self) -> None:
        red_dat = signal.savgol_filter(
            self.history_red,
            window_length = 199,
            polyorder = 5,
            mode = 'interp',
            )[25:self.max_readings - 25]
        vmax: int = max(red_dat)
        vmin: int = min(red_dat)
        center: float = (vmax - (vmax - vmin) / 2)
        self._peaks = signal.find_peaks(
                red_dat,
                prominence = self.pk_prominence,
                height = center,
                distance = self.pk_holdoff,
            )[0]
        print(self._peaks)


    def _save_cal_file(self, file_path: str) -> None:
        """Saves calibration tables to file."""
        logging.info(f"Saving data to save file: {file_path}")
        save_data = {}
        save_data["R_TABLE"] = self._cal_r
        save_data["SPO2_TABLE"] = self._cal_spo2
        try:
            f = open(file_path, 'w')
            json.dump(save_data, f)
            f.close()
        except PermissionError as e:
            logging.warning(f"Could not save calibration file! \n{e}")

    
    def _load_cal_file(self, file_path: str) -> None:
        """
        Loads the JSON file containing the calibration table. If no file 
        is found, load the default values and save those to the file. Updates
        the calibration tables with the values in the file (cal_r and cal_spo2).
        """

        logging.debug(f"Loading calibration file: {file_path}")
        try:
            f = open(file_path, 'r')
            data = json.load(f)
            f.close()
            self._cal_r = data["R_TABLE"]
            self._cal_spo2 = data["SPO2_TABLE"]
        except FileNotFoundError as e:
            logging.warning(e)
            logging.info("Loading default calibration tables.")
            self._cal_r: list = self._default_cal_r
            self._cal_spo2: list = self._default_cal_spo2
            self._save_cal_file(self._cal_file_path)

