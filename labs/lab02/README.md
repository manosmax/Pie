# Section B 
**RQ0: What is the commit hash of your final “end-of-lab” commit for Lab 01?**
The final commit hash, before this update is the following : 05e15202680a32edbde8939962c854a6412d6f5d

---

##  Part A - Understanding the sensor device

**RQ1: Is a PIR sensor active or passive? Contact or no-contact? Explain in your own words.**
The PIR sensor is passive because it does not emit its own energy to scan object. Also it is no-contact because it operates through optical sensor. 

**RQ2: What is the output range/representation of this sensor?**
The output is range is 0-3.3 Volts. The **LOW** range is for when no motion is detected and the **HIGH** range is for when motion is detected.

**RQ3: If TIME is set to 300s, what wrong assumption might your software make about “continuous motion”?**
If an object passes quickly the sensor won't be able to detect the IR signal.

**RQ4: Why does warm-up time matter in real deployments?**
Because it needs time to acclimatize to the room IR level.



---

## Part B — Raspberry Pi GPIO basics (what you are controlling, which pins to use, and why)

**RQ5: Explain a realistic bug that happens when a team mixes BCM and BOARD numbering.**
A signal might me misinterpreted because a team read the pin using onother numbering method.

---
## Part C — Wiring the PIR sensor (step-by-step) and verifying hardware

**RQ6: Fill in the wiring table for your setup (use your actual pins).**

| Sensor Pin | Pi pin (physical) | Pi name (BCM)   | Why |
|------------|-------------------|-----------------|-----|
| `VCC`        | 2                 | 5V|power|
| `GND`        | 6                 | GND|reference|
| `OUT`        | 11                | GPIO17|input signal|

**RQ7: Which GPIO pin did you select (BCM) and why?**
We used the 11th pin (`GPIO17`) because it was the closest to the rest of our wiring and the best option for the sensor connectivity.

**RQ8: Paste the command you ran for the smoke test and a short snippet of output.**
`Input:`python pir_smoke_test.py
`Output:`
Motion stopped \
Motion Detected \
Motion stopped \
Motion Detected \
Motion stopped \
Motion Detected \

**RQ9: With TIME at minimum, approximately how long did OUT remain HIGH after motion?**
With TIME at minimum it took half a second to go from `Motion Detected` to `Motion Stopped`.

**RQ10: With TIME at maximum, approximately how long did OUT remain HIGH after motion?**
With TIME at maximum it took half a second to go from `Motion Detected` to `Motion Stopped`.

**RQ11: What was the maximum distance at which you reliably triggered motion at low sensitivity vs high sensitivity?**
We could not fully see the capabilities of the sensor but after going 3 meters away the sensor could not detect motion at low sensitivity and at high sensitivity the sensor worked after 5 meters away.

**RQ12: Describe the observed difference between H and L mode in your own words (based on your experiment).**
On `L` mode once the sensor is triggered it stays HIGH for a timer cycle, on `H` mode if additional action is detected while the output is high the timer resets and starts again.

---
## Part D — Software setup

**RQ13: Paste your sys.executable output and explain how it proves you are using the venv.**
```bash
(venv) iotlab_upat_8@iotlab-Upat-8:~/programs/Pie/labs/lab02 $ python -c "import sys; print(sys.executable)"
/home/iotlab_upat_8/programs/Pie/labs/lab02/venv/bin/python
```
At the start of the command we see `(venv)` and also the path has `/venv` in the name.

---

## Part E — From “signal” to “event” (core programming)

---

## Part F — GitHub Projects Kanban Board (in your repo): what it is, why we use it, and exactly how to do it


**RQ21: Provide a screenshot of your board .**
<img width="1779" height="1079" alt="image" src="https://github.com/user-attachments/assets/11ffc301-00d8-41cb-bce8-115b419c8fb2" />


**RQ22: Give one concrete example of how the board can prevent a coordination bug (e.g., wrong pin, duplicated work, missed experiment).**

**RQ23: Which card can be a “critical path” blocker for your team, and why?**


