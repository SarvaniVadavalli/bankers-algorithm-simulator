CC=gcc
CFLAGS=-std=c11 -Wall -Wextra -Wpedantic -O2 -D_POSIX_C_SOURCE=200809L -Iinclude
LDFLAGS=-pthread
SOURCES=src/main.c src/protocol.c src/banker.c src/safety.c src/customer.c

all: bankers
bankers: $(SOURCES) include/banker.h include/customer.h include/protocol.h
	$(CC) $(CFLAGS) $(SOURCES) -o $@ $(LDFLAGS)
clean:
	rm -f bankers
.PHONY: all clean
