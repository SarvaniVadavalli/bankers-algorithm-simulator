#ifndef BANKER_H
#define BANKER_H
#include <pthread.h>

typedef struct {
    int customers, resources;
    int *total, *available;
    int **maximum, **allocation, **need;
    pthread_mutex_t mutex;
    int mutex_initialized;
} BankState;

int bank_init(BankState *b, int n, int m, const int *total,
              int *const *maximum, int *const *allocation);
void bank_destroy(BankState *b);
int bank_safety_unlocked(const BankState *b, int *sequence);
int bank_request(BankState *b, int customer, const int *request, int *sequence);
int bank_release(BankState *b, int customer, const int *release);
void bank_snapshot(BankState *b, int *available, int **allocation,
                   int **maximum, int **need, int *safe, int *sequence);

/* Request result codes */
enum { BANK_GRANTED=1, BANK_UNSAFE=0, BANK_EXCEEDS_NEED=-1,
       BANK_UNAVAILABLE=-2, BANK_INVALID=-3 };
#endif
