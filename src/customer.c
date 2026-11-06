#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "customer.h"

static pthread_mutex_t output_mutex = PTHREAD_MUTEX_INITIALIZER;

void *customer_thread(void *arg) {
    CustomerArgs *a = arg;
    BankState *b = a->bank;
    int *seq = calloc((size_t)b->customers, sizeof(int));

    pthread_mutex_lock(&output_mutex);
    printf("{\"event\":\"customer_started\",\"customer\":%d}\n", a->id);
    fflush(stdout);
    pthread_mutex_unlock(&output_mutex);

    int result = bank_request(b, a->id, a->request, seq);

    pthread_mutex_lock(&output_mutex);
    printf("{\"event\":\"request_result\",\"customer\":%d,\"result\":%d,\"safe_sequence\":[", a->id, result);
    if (result == BANK_GRANTED && seq) {
        for (int i = 0; i < b->customers; i++) {
            printf("%s%d", i ? "," : "", seq[i]);
        }
    }
    printf("]}\n");
    fflush(stdout);
    pthread_mutex_unlock(&output_mutex);

    if (result == BANK_GRANTED) {
        struct timespec ts = {a->delay_ms / 1000, (long)(a->delay_ms % 1000) * 1000000L};
        nanosleep(&ts, NULL);

        int rel_ok = bank_release(b, a->id, a->request);

        pthread_mutex_lock(&output_mutex);
        if (rel_ok) {
            printf("{\"event\":\"customer_released\",\"customer\":%d}\n", a->id);
        } else {
            printf("{\"event\":\"release_failed\",\"customer\":%d}\n", a->id);
        }
        fflush(stdout);
        pthread_mutex_unlock(&output_mutex);
    }

    free(seq);
    return NULL;
}
