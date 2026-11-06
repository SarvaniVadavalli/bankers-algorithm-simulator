#ifndef CUSTOMER_H
#define CUSTOMER_H
#include "banker.h"
typedef struct { BankState *bank; int id; int *request; int delay_ms; } CustomerArgs;
void *customer_thread(void *arg);
#endif
