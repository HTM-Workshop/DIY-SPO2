import statistics as stat
import math, numpy, pickle

class SPO2:
    def __init__(self):
        self.r_value_history_max = 100
        self.r_value_history = [0] * self.r_value_history_max
        self.raw_red = list()
        self.raw_ir  = list()
        self.rms_red = 0.0
        self.rms_ir  = 0.0
        self.r_value = 0.0
        self.max_readings = 80
        self.heart_rate = 0.0
        self.default_calb_r    = [0.4, 0.85, 0.98, 1.1, 10]
        self.default_calb_spo2 = [100, 97, 96, 95, 0]
        self.calb_r = list()
        self.calb_spo2 = list()

        # load saved calibration 
        self.load_file()
    def add_reading(self, list_in):
        self.raw_red.append(list_in[0])
        self.raw_ir.append(list_in[1])
        if(len(self.raw_red) > self.max_readings):
            self.raw_red.pop(0)
            self.raw_ir.pop(0)
    def update_rms(self):
        try:
            self.rms_red = calc_rms(self.raw_red)
            self.rms_ir  = calc_rms(self.raw_ir)
        except:
            pass
    def calc_r(self):
        red_mean = stat.mean(self.raw_red)
        ir_mean  = stat.mean(self.raw_ir)
        norm_red = list()
        norm_ir  = list()
        for i in self.raw_red:
            norm_red.append(i - red_mean)
        for i in self.raw_ir:
            norm_ir.append(i - ir_mean)
        self.rms_red = calc_rms(norm_red)
        self.rms_ir  = calc_rms(norm_ir)
        self.r_value = (self.rms_red / self.rms_ir)
        self.r_value_history.append(self.r_value)
        self.r_value_history.pop(0)
    def calc_r_avg(self):
        val = sum(self.r_value_history) 
        return val / self.r_value_history_max
    def reset(self):
        self.raw_red = list()
        self.raw_ir  = list()

    # This algorithm is a bit screwy. It tries to find two consecutive peaks in the 
    # recorded data and calculate the time difference between them. Problem is that 
    # the noisy signal fools the algorithm pretty easily, causing it to give bad values
    # A "peak" is defined as three consecutive data points that have been increasing
    # in value:  i.e.  A < B < C
    def detect_heart_rate(self, rate):
        history = [999, 999, 999]
        start_point = 0

        # The minimum delta between the datapoints in order to accept the peak
        min_variation = 0.5
        
        # first pass, find first peak and ignore it
        # necessary as it may begin this algorithm in the middle of a heart beat
        # and get bad values
        for i, v in enumerate(self.raw_ir):
            history.append(v)
            history.pop(0)
            if(is_list_rising(history)):
                if((history[2] - history[0]) > min_variation):
                    start_point = i
                    print("START: " + str(i) + ", " + str(v))
                    break

        # second pass, find first "real" peak
        history = [999, 999, 999]
        for i, v in enumerate(self.raw_ir[start_point + 1:]):
            history.append(v)
            history.pop(0)
            if(is_list_rising(history)):
                if((history[2] - history[0]) > min_variation):
                    point1 = i + start_point
                    print("Point 1: " + str(point1) + ", " + str(v))
                    break

        # final pass, find second peak
        history = [999, 999, 999]
        for i, v in enumerate(self.raw_ir[point1 + 1:]):
            history.append(v)
            history.pop(0)
            if(is_list_rising(history)):
                if((history[2] - history[0]) > min_variation):
                    point2 = i + point1
                    print("Point 2: " + str(point2) + ", " + str(v))
                    break

        # if either point has failed, skip calculation
        if(point1 == 0 or point2 == 0):
            return False
        else:
            self.heart_rate = 1 / ((point2 - point1) * rate)
            self.heart_rate = self.heart_rate * 60 * 1000
            print("CALCUALTED RATE: " + str(self.heart_rate))
    def dump_all(self):
        print(self.raw_red)
        print(self.raw_ir)
    def set_cal(r_list, spo2_list):
        assert(len(r_list) == len(spo2_list))
        self.calb_r    = r_list
        self.calb_spo2 = spo2_list 

    # call set_cal() method to set calibration coefficients before calling this
    def calc_spo2(self):
        sp = numpy.interp(self.calc_r_avg(), self.calb_r, self.calb_spo2)
        return round(sp)
    def load_file(self):
        try:
            f = open('r_curve.pkl', 'rb')
            self.calb_r = pickle.load(f)
            self.calb_spo2 = pickle.load(f)
            f.close()
        except:
            self.calb_r = self.default_calb_r
            self.calb_spo2 = self.default_calb_spo2
            f = open('r_curve.pkl', 'wb')
            pickle.dump(self.calb_r, f)
            pickle.dump(self.calb_spo2, f)
            f.flush()
            f.close()
    def save_file(self):
        f = open('r_curve.pkl', 'wb')
        pickle.dump(self.calb_r, f)
        pickle.dump(self.calb_spo2, f)
        f.flush()
        f.close()


def is_list_rising(list_in):
    if(list_in[0] < list_in[1] and list_in[1] < list_in[2]):
        return True
    else:
        return False

def calc_rms(list_in):
    total = 0
    for i in list_in:
        total = total + (i ** 2)
    total = total / len(list_in)
    return math.sqrt(total)
