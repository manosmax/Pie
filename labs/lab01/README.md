## Team 8: Report LAB 1

**Team Members:**
* Anastasios Kanellopoulos
* Pasamihalis Emmanouil
* Giakoumakis Emmanouil

---

### General Information

**Report Question (RQ0): What is the commit hash of your final “end-of-lab” commit for Lab 01?**
*(Please insert your commit hash here)*

---

### Part 1: Networking & SSH Setup

**RQ1. What hostname and IP address did you use?**
We used hostname: `iotlab-Ulab8` and the ip address `10.184.45.237` visible in the following screenshot to connect to our Pi using SSH.

**RQ2: Did DNS resolution work (ping google.com)? If it failed, what does that imply?**
After successfully connecting to the internet we were able to normally browse and ping any website that we needed.

**RQ3: Was the connection wired or wireless?**
We used a wireless connection. Using our laptop as a portable wi-fi hotspot we were able to connect our Pi to the laptop which was connected to the eduroam network.

**RQ4: Which method did you use to enable SSH (GUI or raspi-config)? List the exact steps.**
We used the 1st method (GUI) to enable SSH in our Pi. We navigated to **Menu -> Preferences -> Raspberry Pi Configuration** and then we set SSH to enabled in the Interfaces Tab. After clicking finished we rebooted the Pi to make sure that our configuration would work as expected.

**RQ5: What command did you run to verify that SSH is active? Include the relevant output snippet.**
*(Please insert output snippet here)* We used the command `systemctl status ssh` which showed us that the service was not only enabled but also active.

**RQ6: In your own words, why is SSH a necessary tool for managing edge devices after deployment?**
It is very important to mention that some edge devices can be inaccessible after deployment so there needs to be a way to control them without the need to plug in a keyboard and mouse or a display (“headless”). It also allows for secure access to change parameters, update and configure the device.

**RQ6(2): What SSH command did you use, and which username?**
*(Please insert output snippet here)*

**RQ7: Did you see a host key prompt the first time? What is that prompt for (in your own words)?**
*(Please insert output snippet here)*

**RQ8: What does uptime tell you that is relevant for edge systems?**
Uptime is extremely important for edge systems as it can provide critical information about any software and hardware crashes as well as any power interrupts. As edge systems often handle data, by examining uptime we can look out for any data loss that might have occurred during a crash or power outage. To conclude, uptime is a key diagnostic tool for any factors that can affect the stability of our edge device.

**RQ9: Did you enable SSH keys? describe the steps briefly.**
We did not enable SSH keys as our login process is already very straight forward.

**RQ10: Why are SSH keys generally preferred over passwords for remote access?**
While passwords can easily be guessed, brute-forced, forgotten or leaked, SSH keys are extremely long and practically impossible to brute-force. Also SSH keys can provide an easier and more secure way for automated authentication for anything in our edge environment that needs non-interactive login.

---

### Part 2: System Configuration & Git Version Control

**RQ11: Is system time correct? If not, what could break downstream (give two examples)?**
The system time was correct after setting up the machine and connecting it to the internet. If the time were to malfunction it would present problems if we needed our edge system to activate at a specific time. Alternatively, if we were to receive logs from our device to diagnose an issue the timestamp would be off. 

**RQ12: How much free disk space is available? Why does disk usage matter for logging systems?**
29Gb total available, 21Gb free. 
*(Please add why disk usage matters for logging systems here)*

**RQ13: What Python version is installed? Why might the Python version affect reproducibility?**
Our Pi has Python `3.13.5` installed. Python version can affect reproducibility as changes in language features, standard libraries, or dependency compatibility, may cause code to behave differently or even fail across environments.

**RQ14: Who created the repository and how did you grant access to teammates (briefly)?**
Manolis Pasamichalis created the repository and the other members were invited as collaborators. After they accepted, they were able to commit to the repository.

**RQ15: What would likely go wrong if each team member kept their own local version of the lab/project work?**
If each team member kept their own local version of the project, each one of us would be working on a separate version. That would mean that we would not know which file was truly the latest and that we would need to manually merge the files together. Also, we would not have a history of the changes each one of us has contributed, so debugging would be harder. Dependencies can break as there could be wrong code integration.

**RQ16: What is the difference between git add and git commit (in your own words)?**
The difference between `git add` and `git commit` is that `git add` selects what changes should be added in the next update. `git commit` finalizes those changes and saves them to a local repository.

**RQ17: What does git push do, and why is it important in a team setting?**
Finally `git push` adds the changes that were saved by `git commit` to the online repository where everyone in the team can view the commits. It is important in a team setting because the team can pull your changes and integrate them to their local repository where they can continue working on the latest version of the file.

**RQ18: What problem can happen if two teammates edit the same file without pulling first?**
If two teammates edit the same file without pulling first they would not be editing the latest version of the project. That would mean that there could be crashes or bugs when they integrate their code in the project down the line because they would not take into account each other's contribution.

**RQ19: Did your team use branches? If yes, describe your workflow briefly. If no, explain why.**
Our team did not use branches in the first lab as the process was too simple. We just updated the online repository every time each one of us made a change so everyone would be in the latest version.

**RQ20: What is a merge conflict, and when does it happen?**

A merge conflict occurs when Git cannot automatically merge changes from two branches because the changes overlap or contradict each other. It typically happens when two people modify the same lines in the same file, one branch deletes a file while another branch modifies it, or the same section of code is edited differently in separate branches.

**RQ21: Which authentication method did you use to push to GitHub (HTTPS+token, SSH key, other)? Why?**
Because of our previous experience with GitHub, for personal use and other courses such as “Βάσεις Δεδομένων”, we each had a GitHub Personal Access Token that we used for authentication.

**RQ22: Why should virtual environments not be committed to git?**
Virtual environments should not be committed to git as they contain packages that are already committed in `requirements.txt` so committing them again would bloat the repository. The correct approach is for each developer to create their own virtual environments based on the committed `requirements.txt` file.

**RQ23: Why is it usually not acceptable to commit logs?**
It is usually not acceptable to commit logs as they are usually very large files that can contain sensitive information such as system paths and API keys. Logs are temporary and environment-specific so they should be excluded via `.gitignore`.

**RQ24: Where on the Pi did you clone the repo (path)? Why did you choose that location?**
We chose to clone the repository into a new file named `programs` at the home path for easy and quick access. As our device is used only for the labs and the final project, keeping the cloned repository on the home path is the best choice for frequent access.

---
**RQ25:What did sys.executable show, and how does that prove you are using the venv?**

The sys.executable shows:

(venv) iotlab_upat_8@iotlab-Upat-8:~/programs/Pie/labs/lab01 $ python -c "import sys; print(sys.executable)"
/home/iotlab_upat_8/programs/Pie/labs/lab01/venv/bin/python

We can confirm that we are using venv in two ways as seen by the underlined characters above.

---

** RQ26:In one paragraph: what problem does a venv solve?**

A virtual environment solves the problem of dependency conflicts between projects by isolating each project’s packages and versions from the system installation. A virtual environment creates a self-contained space where dependencies can be installed, managed, and reproduced independently, ensuring consistent behavior across development environments and preventing “it works on my machine” issues.

---

**RQ27:What dependencies did you include and why? If you use argparse do you need to include the requirements.txt, if not why?**

We used click as it is recommended and seems to offer a more modern way to create a structured CLI library.

---

**RQ28:What would happen if different teams used different dependency versions?**
Due to differences in library functions the code will not work properly on all computers and will not be reproducible.

---

**RQ29:How can you verify you installed packages into the venv (not the system Python)? Give one command and explain what you look for.**

We can use pip list to see all the available packages when we are at the venv terminal. There we will see a list of all the available packages that we can use for our project.

---

**RQ31:Why might it be useful to start with a mock event generator instead of connecting real hardware immediately?**

We need to use a controlled environment at first to check for stability issues and the correct function of the program before using real hardware in a real world scenario, which introduces noise and unforeseen circumstances which can affect our measurements.

---

**RQ32:What aspects of the system can you test with this mock that are independent of sensors?**

We can confirm that we can successfully log our data and access them remotely through the network. We can also simulate data for statistical analysis.

---

**RQ33:Why is it useful to distinguish between “activity” events (like deposit) and “liveness” events (like heartbeat)?**

Activity events don't happen on a regular basis but only when an action is performed. While heartbeat events happen regularly to indicate the device’s online status and proper function and communication with our systems.

---

**RQ34:Give one example of how a system might misbehave if heartbeats were missing.**

In case the system goes offline without heartbeat messages, we will not detect the issue in time and we may lose important activity data.

---
**RQ35: Which optional parameters (if any) did you add, and why?**

We added verbose and starting total on our code. Starting total allowed us to know the exact number of logs despite restarts and verbose can inform us in the terminal when running the programm.

---
**RQ36: Why is it important that invalid CLI arguments fail early and clearly?**

It is important in order to understand that we executed the programm with wrong parameters.

---
**RQ37: Why is JSON Lines a good fit for append-only event logs?**

Because each event is stored as a separate JSON object on its own line. This makes it easy to append new events to the end of the file without modifying existing data. It also allows the log to be processed incrementally, since each line can be read and parsed independently. JSON Lines is easy to debug, and compatible with many tools and programming languages, making it practical for logging and data analysis.

---
**RQ38: Why is it useful to include both seq and timestamps in each record?**
They are two different types of information. Seq allows us to enumerate the deposits while timestamps inform us of when the deposits happen. 

---
**RQ39: Why should deposit_total be monotonically increasing within a run?**
deposit_total should be monotonically increased to preserve the order of the deposit events.