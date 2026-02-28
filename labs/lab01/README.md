# Team 8: Report LAB 1

**Team Members:**
* **Anastasios Kanellopoulos**
* **Pasamihalis Emmanouil**
* **Giakoumakis Emmanouil**

---


**RQ0: What is the commit hash of your final “end-of-lab” commit for Lab 01?**
> ..

---

##  Part A — One-time Raspberry Pi bootstrap

**RQ1: What hostname and IP address did you use?**
We used hostname: `iotlab-Ulab8` and the IP address `10.184.45.237`.

**RQ2: Did DNS resolution work (ping google.com)? If it failed, what does that imply?**
After successfully connecting to the internet we were able to normally browse and ping any website that we needed.If it failed it would mean that we have not connected successfully on the internet. 

**RQ3: Was the connection wired or wireless?**
We used a wireless connection. Using our laptop as a portable Wi-Fi hotspot, we were able to connect our Pi to the laptop which was connected to the eduroam network.

**RQ4: Which method did you use to enable SSH (GUI or raspi-config)? List the exact steps.**
We used the **GUI** method:
1.  Navigated to **Menu -> Preferences -> Raspberry Pi Configuration**.
2.  Selected the **Interfaces** tab.
3.  Set **SSH** to **Enabled**.
4.  Clicked **Finished** and rebooted the Pi to ensure the configuration was active.

**RQ5: What command did you run to verify that SSH is active? Include the relevant output snippet.**
We used the command `systemctl status ssh` which showed us that the service was not only enabled but also active.

**RQ6: In your own words, why is SSH a necessary tool for managing edge devices after deployment?**
Edge devices are often inaccessible after deployment (e.g., mounted high up or in remote locations). SSH allows us to manage them "headless" without needing a physical keyboard or monitor. It provides a secure way to update code, change parameters, and perform diagnostics.

---

## Part B — Remote-first workflow (SSH from laptop)


**RQ7: What SSH command did you use, and which username?**
We used the command `ssh iotlab_upat_8@10.184.45.237` using the username `iotlab_upat_8`.

**RQ8: Did you see a host key prompt the first time? What is that prompt for (in your own words)?**
Yes, we saw a host key prompt. This is a security feature that allows the client to verify the identity of the remote server. By accepting the key, we ensure that we are connecting to the intended device and not an unauthorized one (protecting against Man-in-the-Middle attacks).

**RQ9: What does uptime tell you that is relevant for edge systems?**
Uptime is extremely important for edge systems as it can provide critical information about any software and hardware crashes as well as any power interrupts. As edge systems often handle data, by examining uptime we can look out for any data loss that might have occurred during a crash or power outage. To conclude, uptime is a key diagnostic tool for any factors that can affect the stability of our edge device.

**RQ10: Did you enable SSH keys? Describe the steps briefly.**
We did not enable SSH keys as our login process is already very straight forward.


**RQ11: Why are SSH keys generally preferred over passwords for remote access?**
While passwords can easily be guessed, brute-forced, forgotten or leaked SSH keys are extremely long and practically impossible to brute-force. Also SSH keys can provide an easier and more secure way for automated authentication for anything in our edge environment that needs non-interactive login.

---

## Part C — Baseline smoke test

**RQ12: Is system time correct? If not, what could break downstream?**
The system time was correct after setting up the machine and connecting it to the internet. If the time were to malfunction it would present problems if we needed our edge system to activate at a specific time. Alternatively, if we were to receive logs from our device to diagnose an issue the timestamp would be off. 

**RQ13: How much free disk space is available? Why does disk usage matter for logging systems?**
* **Total:** 29 GB | **Free:** 21 GB
* In case of storing logs or other critical data,we need to monitor if we run out of space.

**RQ14: What Python version is installed? Why might the Python version affect reproducibility?**
Our Pi has Python `3.13.5` installed. Python version can affect reproducibility as changes in language features, standard libraries, or dependency compatibility may cause code to behave differently or fail across environments.

**RQ15: Who created the repository and how did you grant access to teammates?**
Manolis Pasamichalis created the repository. Teammates were invited as GitHub collaborators and accepted the invitation to gain commit access.

---
## Part D — Git and GitHub basics 

**RQ16: What would likely go wrong if each team member kept their own local version of the lab/project work?**
If each team member kept their own local version of the project, each one of us would be working on a separate version. That would mean that we would not know which file was truly the latest and that we would need to manually merge the files together. Also, we would not have a history of the changes each one of us has contributed, so debugging would be harder. Dependencies can break as there could be wrong code integration.

**RQ17: What is the difference between git add and git commit?**
* `git add`: Selects which changes should be added to the next update .
* `git commit`: Finalizes those changes and saves them in the local repository.

**RQ18: What does git push do, and why is it important in a team setting?**
Finally git push adds the changes that were saved by git commit to the online repository where everyone in the team can view the commits. It is important in a team setting because the team can pull your changes and integrate them to their local repository where they can continue working on the latest version of the file.

**RQ19: What problem can happen if two teammates edit the same file without pulling first?**
If two teammates edit the same file without pulling first they would not be editing the latest version of the project. That would mean that there could be crashes or bugs when they integrate their code in the project down the line because they would not take into account each other's contribution.

**RQ20: Did your team use branches? If yes, describe your workflow briefly. If no, explain why.**
Our team did not use branches in the first lab as the process work too simple. We just updated the online repository every time each one of us made a change so everyone would be in the latest version.

**RQ21: What is a merge conflict, and when does it happen?**
A merge conflict occurs when Git can not automatically merge changes from two branches because the changes overlap or contradict each other.It typically happens when two people modify the same lines in the same file,one branch deletes a file while another branch modifies it,the same section of code is edited differently in separate branches.

**RQ22: Which authentication method did you use to push to GitHub?**
Because of our previous experience with git hub, for personal use and other courses such as “Βάσεις Δεδομένων”, we each had a GitHub Personal Access Token that we used for authentication.

**RQ23: Why should virtual environments not be committed to git?**
Virtual environments should not be committed to git as they contain packages that are already committed in requirements.txt so committing them again would bloat the repository. The correct approach is for each developer to create their own virtual environments based on the committed requirements.txt file.

**RQ24: Why is it usually not acceptable to commit logs?**
It is usually not acceptable to commit logs as they are usually very large files that can contain sensitive information such as system paths and API keys. Logs are temporary and environment-specific so they should be excluded via `.gitignore`.

**RQ25: Where on the Pi did you clone the repo (path)? Why?**
We chose to clone the repository into a new file named `~\programs` at the home path for easy and quick access. As our device is used only for the labs and the final project, keeping the cloned repository on the home path is the best choice for frequent access.

---

## 🐍 Part C: Reproducible Python environment on the Pi

**RQ26: What did sys.executable show, and how does that prove you are using the venv?**
It showed: `/home/iotlab_upat_8/programs/Pie/labs/lab01/venv/bin/python`.
The explicit path pointing to the `venv` folder confirms the interpreter is isolated within the project environment.

**RQ27: In one paragraph: what problem does a venv solve?**
A virtual environment solves the problem of dependency conflicts by isolating each project’s packages from the system installation. It creates a self-contained space where dependencies can be managed independently, ensuring consistent behavior across development environments and preventing "it works on my machine" issues.

**RQ28: What dependencies did you include and why? If you use argparse do you need to include the requirements.txt?**
We used `click` as it is a modern, recommended way to create structured CLI libraries. If using `argparse`, you don't strictly *need* it in `requirements.txt` because it is a standard library, but it's often included for clarity.

**RQ29: What would happen if different teams used different dependency versions?**
Due to differences in library functions, the code might not work properly on all computers, leading to a lack of reproducibility.

**RQ30: How can you verify you installed packages into the venv?**
Run `pip list` within the activated environment. It will display only the packages installed specifically for that project.

---

## 📈 Part F: Logic & Data Logging

**RQ31: Why might it be useful to start with a mock event generator instead of real hardware?**
It allows for testing software stability in a controlled environment before introducing the "noise" and unpredictable variables of real-world hardware.

**RQ32: What aspects of the system can you test with this mock that are independent of sensors?**
We can verify that data is logged successfully, that the network access works, and that the data is structured correctly for statistical analysis.

**RQ33: Why is it useful to distinguish between “activity” (deposit) and “liveness” (heartbeat) events?**
Activity events are sporadic (only when an action occurs), whereas heartbeats are regular and indicate the device is still online and communicating properly even during idle periods.

**RQ34: Give one example of how a system might misbehave if heartbeats were missing.**
If the system goes offline, we would not detect the failure until a "deposit" was expected, potentially leading to significant data loss during the undetected downtime.

**RQ35: Which optional parameters (if any) did you add, and why?**
We added `--verbose` (to see real-time updates in the terminal) and `--starting-total` (to maintain record continuity across restarts).

**RQ36: Why is it important that invalid CLI arguments fail early and clearly?**
It ensures the user immediately knows they have executed the program with incorrect parameters, preventing errors further down the line.

**RQ37: Why is JSON Lines a good fit for append-only event logs?**
Each line is an independent object. This allows for easy appending, incremental processing (reading line-by-line), and keeps the log readable and easy to debug.

**RQ38: Why is it useful to include both seq and timestamps in each record?**
`seq` provides a strict numerical order of deposits, while `timestamps` provide the real-world time of the event.

**RQ39: Why should deposit_total be monotonically increasing within a run?**

It preserves the logical order of events and ensures that no data has been lost or calculated incorrectly during the process.


**RQ40: Which of the above correctness rules would be hardest to verify manually, and why?**

The hardest rule to verify manualy is the monotonical character of the seq. An error would be difficult to spot across thousands of records by hand.

**RQ41: What problems arise if operational messages are mixed into event logs?**

Operational messages are of different format from event logs. Mixing the streams would possibly break the json file which even though not hard to spot manually, would create problems for programms that automatically access it, possibly breaking them. 

**RQ42: Why might operational logs still be essential during debugging?**

The heartbeat records can identify when the controller for some reason fails. However we don't get any information about the reason of the crash. For debugging purposes, it is usefull to log operational logs so that we know where the problem occured and what to try to fix. 

**RQ43: Why is it important to distinguish usage errors from runtime errors?**

Usage errros do not indicate a problem with the program but are examples of of human error. The user just needs to re-examine his commands. Distinguishing them from runtime errors, enables the microcontroller to inform the developers about the issue or not. 


**RQ44: How could consistent exit codes be useful in automated systems?**

Replacing print statements with error codes gives a more compatible output with automated systems. Those codes tell the automated program exactly how to respond to each kind of crash. 

**RQ45: What could go wrong if a program is terminated without handling interrupts properly?**

A sudden program termination could break files and logs. The proccess could be stopped in the middle of writting a line. This breaks the json format and currupts the logs.


**RQ46: Show the first and last JSON record produced by this test and explain how the counters changed.**


***FIRST RECORD***
```json
{
"device_id": "wastebin-01", 
"event_type": "deposit", 
"seq": 1, 
"timestamp": "2026-02-27T15:30:00Z", 
"deposit_delta": 1, 
"deposit_total": 1, 
"run_id": "123"
}
```

***LAST RECORD***
```json
{
"device_id": "wastebin-01", 
"event_type": "deposit", 
"seq": 10, 
"timestamp": "2026-02-27T15:30:00.8Z", 
"deposit_delta": 1, 
"deposit_total": 10, 
"run_id": "123"
}
```

From the records above we can see that the seq and the total increasing by one with each event reached 10. The delta is 1 as every event increases the deposit_total by 1. 

**RQ47: How can a consumer distinguish heartbeat records from deposit records in the log?**

A user can easily distinguish the two types of records with the record at the event_type key 


**RQ48: For each invalid command, show the error message and exit code.**
>....

**RQ49: Which invalid input do you think is most likely in real usage, and why?**

The most likely are are either gramatical in nature or forgetting set some of them. 

**RQ50: How many records were written before interruption?**

Before interrupting the program, wtih one record per second, there we written 10 records on the log file.
