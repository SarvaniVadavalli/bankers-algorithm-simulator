#include <stdlib.h>
#include <string.h>
#include "banker.h"

static int **matrix_new(int rows, int cols) {
    int **a = calloc((size_t)rows, sizeof(*a));
    if (!a) return NULL;
    for (int i=0;i<rows;i++) {
        a[i] = calloc((size_t)cols, sizeof(**a));
        if (!a[i]) { for (int k=0;k<i;k++) free(a[k]); free(a); return NULL; }
    }
    return a;
}
static void matrix_free(int **a, int rows) {
    if (!a) return;
    for (int i=0;i<rows;i++) free(a[i]);
    free(a);
}
static void recalc(BankState *b) {
    for (int j=0;j<b->resources;j++) {
        int used=0;
        for (int i=0;i<b->customers;i++) used += b->allocation[i][j];
        b->available[j] = b->total[j] - used;
    }
    for (int i=0;i<b->customers;i++)
        for (int j=0;j<b->resources;j++)
            b->need[i][j] = b->maximum[i][j] - b->allocation[i][j];
}
int bank_init(BankState *b, int n, int m, const int *total,
              int *const *maximum, int *const *allocation) {
    if (!b || n<1 || n>50 || m<1 || m>10 || !total || !maximum || !allocation) return 0;
    memset(b,0,sizeof(*b)); b->customers=n; b->resources=m;
    b->total=calloc((size_t)m,sizeof(int)); b->available=calloc((size_t)m,sizeof(int));
    b->maximum=matrix_new(n,m); b->allocation=matrix_new(n,m); b->need=matrix_new(n,m);
    if (!b->total || !b->available || !b->maximum || !b->allocation || !b->need) { bank_destroy(b); return 0; }
    for (int j=0;j<m;j++) { if (total[j]<0 || total[j]>1000) { bank_destroy(b); return 0; } b->total[j]=total[j]; }
    for (int i=0;i<n;i++) for (int j=0;j<m;j++) {
        if (maximum[i][j]<0 || allocation[i][j]<0 || allocation[i][j]>maximum[i][j]) { bank_destroy(b); return 0; }
        b->maximum[i][j]=maximum[i][j]; b->allocation[i][j]=allocation[i][j];
    }
    for (int j=0;j<m;j++) { int used=0; for(int i=0;i<n;i++) used+=b->allocation[i][j]; if(used> b->total[j]) { bank_destroy(b); return 0; } }
    if (pthread_mutex_init(&b->mutex,NULL)!=0) { bank_destroy(b); return 0; }
    b->mutex_initialized=1; recalc(b); return 1;
}
void bank_destroy(BankState *b) {
    if (!b) return;
    if (b->mutex_initialized) pthread_mutex_destroy(&b->mutex);
    free(b->total); free(b->available);
    matrix_free(b->maximum,b->customers); matrix_free(b->allocation,b->customers); matrix_free(b->need,b->customers);
    memset(b,0,sizeof(*b));
}
int bank_safety_unlocked(const BankState *b, int *seq) {
    int *work=malloc((size_t)b->resources*sizeof(int));
    int *finish=calloc((size_t)b->customers,sizeof(int));
    if (!work || !finish) { free(work); free(finish); return 0; }
    memcpy(work,b->available,(size_t)b->resources*sizeof(int));
    int done=0;
    while(done<b->customers) {
        int found=0;
        for(int i=0;i<b->customers;i++) if(!finish[i]) {
            int possible=1;
            for(int j=0;j<b->resources;j++) if(b->need[i][j]>work[j]) { possible=0; break; }
            if(possible) { for(int j=0;j<b->resources;j++) work[j]+=b->allocation[i][j]; finish[i]=1; if(seq) seq[done]=i; done++; found=1; }
        }
        if(!found) { free(work); free(finish); return 0; }
    }
    free(work); free(finish); return 1;
}
int bank_request(BankState *b, int c, const int *r, int *seq) {
    if(!b || !r || c<0 || c>=b->customers) return BANK_INVALID;
    pthread_mutex_lock(&b->mutex);
    for(int j=0;j<b->resources;j++) {
        if(r[j]<0) { pthread_mutex_unlock(&b->mutex); return BANK_INVALID; }
        if(r[j]>b->need[c][j]) { pthread_mutex_unlock(&b->mutex); return BANK_EXCEEDS_NEED; }
        if(r[j]>b->available[j]) { pthread_mutex_unlock(&b->mutex); return BANK_UNAVAILABLE; }
    }
    for(int j=0;j<b->resources;j++) { b->available[j]-=r[j]; b->allocation[c][j]+=r[j]; b->need[c][j]-=r[j]; }
    if(bank_safety_unlocked(b,seq)) { pthread_mutex_unlock(&b->mutex); return BANK_GRANTED; }
    for(int j=0;j<b->resources;j++) { b->available[j]+=r[j]; b->allocation[c][j]-=r[j]; b->need[c][j]+=r[j]; }
    pthread_mutex_unlock(&b->mutex); return BANK_UNSAFE;
}
int bank_release(BankState *b, int c, const int *r) {
    if(!b || !r || c<0 || c>=b->customers) return 0;
    pthread_mutex_lock(&b->mutex);
    for(int j=0;j<b->resources;j++) if(r[j]<0 || r[j]>b->allocation[c][j]) { pthread_mutex_unlock(&b->mutex); return 0; }
    for(int j=0;j<b->resources;j++) { b->allocation[c][j]-=r[j]; b->available[j]+=r[j]; b->need[c][j]+=r[j]; }
    pthread_mutex_unlock(&b->mutex); return 1;
}
void bank_snapshot(BankState *b, int *av, int **al, int **mx, int **nd, int *safe, int *seq) {
    pthread_mutex_lock(&b->mutex);
    memcpy(av,b->available,(size_t)b->resources*sizeof(int));
    for(int i=0;i<b->customers;i++) for(int j=0;j<b->resources;j++) { al[i][j]=b->allocation[i][j]; mx[i][j]=b->maximum[i][j]; nd[i][j]=b->need[i][j]; }
    *safe=bank_safety_unlocked(b,seq); pthread_mutex_unlock(&b->mutex);
}
