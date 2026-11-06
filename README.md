# Banker's Algorithm Resource Management Simulator

A dynamic Banker's Algorithm simulator built using C, POSIX Pthreads, and Python Tkinter. It demonstrates deadlock avoidance, concurrent resource allocation, thread synchronization, and resource management through an interactive graphical interface.

## Features

- Dynamic configuration: 1–50 customers and 1–10 resource types.
- Dynamic Maximum, Allocation, Need, and Available matrices.
- Banker's Safety Algorithm and safe-sequence detection.
- Resource request validation and rollback of unsafe requests.
- Resource allocation and release.
- Concurrent customer execution using POSIX Pthreads.
- Mutex-based synchronization.
- Tkinter graphical user interface.
- JSON Lines communication between C backend and Python frontend.
- Dashboard, Configuration, Manual Mode, and Automatic Mode.
- Live customer thread monitoring and activity logs.
- Regression tests for reliability and GUI behaviour.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | C (C11) |
| Concurrency | POSIX Pthreads |
| Synchronization | Pthread Mutex |
| Frontend | Python Tkinter |
| Communication | JSON Lines |
| Compiler | GCC |
| Build | GNU Make |
| Testing | Python unittest |

## Project Structure

```text
bankers-algorithm-simulator/
├── src/
│   ├── main.c
│   ├── protocol.c
│   ├── banker.c
│   ├── safety.c
│   └── customer.c
├── include/
│   ├── banker.h
│   ├── customer.h
│   └── protocol.h
├── frontend/
│   ├── api.py
│   ├── main.py
│   ├── app.py
│   ├── dashboard.py
│   ├── configuration.py
│   ├── manual_mode.py
│   ├── automatic_mode.py
│   ├── styles.py
│   └── test_*.py
├── Makefile
├── README.md
└── .gitignore
