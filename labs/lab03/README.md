**RQ1: Which lecture pipeline phases do you believe you had already implemented in Lab 02?**
**RQ2: Which part of your Lab 02 code did you reuse directly?**
**RQ3: Which part did you have to adapt for the pipeline architecture?**
**RQ4: In your own words, why is a queue useful between acquisition and writing?**
**RQ5: What is backpressure?**
**RQ6: Why can a slow writer become a data acquisition problem and not just a storage problem?**
**RQ7: Is your current edge pipeline closer to ETL or ELT? Explain briefly.**
**RQ8: What transformation already happens before your data is written to disk?**
**RQ9: Give one example of a transformation that could be moved later to another stage of the system.**
**RQ10: Explain the responsibility of the producer in one sentence.**
**RQ11: Explain the responsibility of the consumer in one sentence.**
**RQ12: Show two example JSONL records from your output and explain their fields briefly.**
**RQ13: What does pipeline_latency_ms mean in your system?**
**RQ14: What changed when you introduced --consumer-delay 0.5?**
**RQ15: Did the queue absorb the slowdown? Explain briefly using your own observations.**
**RQ16: What is one clear sign, from your terminal status output, that the producer is outrunning the consumer?**
**RQ17: Why is a bounded queue more informative than an unbounded queue during overload?**
**RQ18: Why should status lines stay in the terminal instead of being mixed into the JSONL file?**
**RQ19: Which field lets you group records from the same program execution, and why is that useful?**
**RQ20: Why would an unbounded queue be dangerous on a Raspberry Pi?**
**RQ21: If you later replaced the JSONL writer with another output component, which part of your system could stay almost unchanged and why?**
