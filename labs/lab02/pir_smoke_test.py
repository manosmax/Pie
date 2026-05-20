from gpiozero import MotionSensor
from signal import pause


pir = MotionSensor(17)

def motion_function():
    print("Motion Detected")

def no_motion_function():
    print("Motion stopped")

pir.when_motion = motion_function
pir.when_no_motion = no_motion_function

pause()  # keep the program running
