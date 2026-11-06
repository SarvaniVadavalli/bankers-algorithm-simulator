#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <pthread.h>
#include "banker.h"
#include "customer.h"

#define LINE_CAP 65536
static char line[LINE_CAP];

static const char *skip_ws(const char *p) {
    while (p && *p && isspace((unsigned char)*p)) p++;
    return p;
}

static const char *keypos(const char *s, const char *key) {
    char k[80];
    snprintf(k, sizeof(k), "\"%s\"", key);
    const char *p = s;
    while ((p = strstr(p, k)) != NULL) {
        const char *q = p + strlen(k);
        q = skip_ws(q);
        if (*q == ':') return q + 1;
        p += strlen(k);
    }
    return NULL;
}

static const char *parse_int_val(const char *p, int *out, int max_val) {
    p = skip_ws(p);
    if (!p || !isdigit((unsigned char)*p)) return NULL;
    char *endp = NULL;
    errno = 0;
    unsigned long long v = strtoull(p, &endp, 10);
    if (endp == p || errno == ERANGE || v > (unsigned long long)max_val) return NULL;
    *out = (int)v;
    return endp;
}

static int getint(const char *s, const char *key, int *out, int max_val) {
    const char *p = keypos(s, key);
    if (!p) return 0;
    p = parse_int_val(p, out, max_val);
    if (!p) return 0;
    p = skip_ws(p);
    if (*p != ',' && *p != '}' && *p != '\0') return 0;
    return 1;
}

static const char *parse_exact_vec(const char *p, int n, int *out, int max_val) {
    p = skip_ws(p);
    if (!p || *p != '[') return NULL;
    p++;
    p = skip_ws(p);
    if (n == 0) {
        if (*p != ']') return NULL;
        return p + 1;
    }
    for (int i = 0; i < n; i++) {
        p = parse_int_val(p, &out[i], max_val);
        if (!p) return NULL;
        p = skip_ws(p);
        if (i < n - 1) {
            if (*p != ',') return NULL;
            p++;
            p = skip_ws(p);
        } else {
            if (*p != ']') return NULL;
            p++;
        }
    }
    return p;
}

static int getvec(const char *s, const char *key, int n, int *out, int max_val) {
    const char *p = keypos(s, key);
    if (!p) return 0;
    p = parse_exact_vec(p, n, out, max_val);
    if (!p) return 0;
    p = skip_ws(p);
    if (*p != ',' && *p != '}' && *p != '\0') return 0;
    return 1;
}

static int **newmat(int n, int m) {
    int **a = calloc((size_t)n, sizeof(*a));
    if (!a) return NULL;
    for (int i = 0; i < n; i++) {
        a[i] = calloc((size_t)m, sizeof(**a));
        if (!a[i]) {
            for (int k = 0; k < i; k++) free(a[k]);
            free(a);
            return NULL;
        }
    }
    return a;
}

static void freemat(int **a, int n) {
    if (a) {
        for (int i = 0; i < n; i++) free(a[i]);
        free(a);
    }
}

static const char *parse_exact_mat(const char *p, int n, int m, int **out, int max_val) {
    p = skip_ws(p);
    if (!p || *p != '[') return NULL;
    p++;
    p = skip_ws(p);
    if (n == 0) {
        if (*p != ']') return NULL;
        return p + 1;
    }
    for (int i = 0; i < n; i++) {
        p = parse_exact_vec(p, m, out[i], max_val);
        if (!p) return NULL;
        p = skip_ws(p);
        if (i < n - 1) {
            if (*p != ',') return NULL;
            p++;
            p = skip_ws(p);
        } else {
            if (*p != ']') return NULL;
            p++;
        }
    }
    return p;
}

static int getmat(const char *s, const char *key, int n, int m, int **out, int max_val) {
    const char *p = keypos(s, key);
    if (!p) return 0;
    p = parse_exact_mat(p, n, m, out, max_val);
    if (!p) return 0;
    p = skip_ws(p);
    if (*p != ',' && *p != '}' && *p != '\0') return 0;
    return 1;
}

static void print_ints(const int *a, int n) {
    putchar('[');
    for (int i = 0; i < n; i++) {
        printf("%s%d", i ? "," : "", a[i]);
    }
    putchar(']');
}

static void print_matrix(int **a, int n, int m) {
    putchar('[');
    for (int i = 0; i < n; i++) {
        if (i) putchar(',');
        print_ints(a[i], m);
    }
    putchar(']');
}

/* Heap-allocated bank pointer prevents invalid copying of pthread_mutex_t */
static BankState *bank = NULL;
static int initialized = 0;

static void error(const char *msg) {
    printf("{\"status\":\"error\",\"message\":\"%s\"}\n", msg);
    fflush(stdout);
}

static void snapshot(void) {
    if (!initialized || !bank) {
        error("Bank is not initialized");
        return;
    }
    int *av = calloc((size_t)bank->resources, sizeof(int));
    int *seq = calloc((size_t)bank->customers, sizeof(int));
    int **al = newmat(bank->customers, bank->resources);
    int **mx = newmat(bank->customers, bank->resources);
    int **nd = newmat(bank->customers, bank->resources);
    if (!av || !seq || !al || !mx || !nd) {
        free(av); free(seq);
        freemat(al, bank->customers);
        freemat(mx, bank->customers);
        freemat(nd, bank->customers);
        error("Memory allocation failed during snapshot");
        return;
    }
    int safe = 0;
    bank_snapshot(bank, av, al, mx, nd, &safe, seq);
    printf("{\"status\":\"ok\",\"customers\":%d,\"resources\":%d,\"available\":", bank->customers, bank->resources);
    print_ints(av, bank->resources);
    printf(",\"allocation\":");
    print_matrix(al, bank->customers, bank->resources);
    printf(",\"maximum\":");
    print_matrix(mx, bank->customers, bank->resources);
    printf(",\"need\":");
    print_matrix(nd, bank->customers, bank->resources);
    printf(",\"safe\":%s,\"safe_sequence\":", safe ? "true" : "false");
    if (safe) print_ints(seq, bank->customers); else printf("[]");
    puts("}");
    fflush(stdout);
    free(av);
    free(seq);
    freemat(al, bank->customers);
    freemat(mx, bank->customers);
    freemat(nd, bank->customers);
}

static void handle(char *s) {
    char cmd[40] = {0};
    const char *p = keypos(s, "command");
    if (!p) {
        error("Missing command");
        return;
    }
    p = skip_ws(p);
    if (*p != '\"') {
        error("Invalid command");
        return;
    }
    p++;
    int k = 0;
    while (*p && *p != '\"' && k < 39) cmd[k++] = *p++;

    if (!strcmp(cmd, "initialize")) {
        int n, m;
        if (!getint(s, "customers", &n, 50) || !getint(s, "resources", &m, 10) || n < 1 || n > 50 || m < 1 || m > 10) {
            error("Invalid dimensions (customers 1-50, resources 1-10)");
            return;
        }
        int *t = calloc((size_t)m, sizeof(int));
        int **mx = newmat(n, m);
        int **al = newmat(n, m);
        if (!t || !mx || !al) {
            free(t); freemat(mx, n); freemat(al, n);
            error("Memory allocation failed");
            return;
        }
        if (!getvec(s, "total", m, t, 1000) ||
            !getmat(s, "maximum", n, m, mx, 1000) ||
            !getmat(s, "allocation", n, m, al, 1000)) {
            error("Invalid or missing total/maximum/allocation arrays");
            free(t); freemat(mx, n); freemat(al, n);
            return;
        }

        /* Safe re-initialization: validate new state independently before touching existing bank */
        BankState *new_b = calloc(1, sizeof(BankState));
        if (!new_b) {
            free(t); freemat(mx, n); freemat(al, n);
            error("Memory allocation failed");
            return;
        }
        int ok = bank_init(new_b, n, m, t, mx, al);
        free(t); freemat(mx, n); freemat(al, n);
        if (!ok) {
            free(new_b);
            error("Configuration invalid or memory allocation failed");
            return;
        }

        /* Success: destroy old bank and replace pointer cleanly without copying mutex */
        if (bank) {
            bank_destroy(bank);
            free(bank);
        }
        bank = new_b;
        initialized = 1;
        puts("{\"status\":\"ok\",\"message\":\"Bank initialized\"}");
        fflush(stdout);
        snapshot();

    } else if (!strcmp(cmd, "snapshot") || !strcmp(cmd, "safety_check")) {
        snapshot();

    } else if (!strcmp(cmd, "request") || !strcmp(cmd, "release")) {
        if (!initialized || !bank) {
            error("Bank is not initialized");
            return;
        }
        int c;
        if (!getint(s, "customer", &c, bank->customers - 1) || c < 0 || c >= bank->customers) {
            error("Missing customer");
            return;
        }
        int *r = calloc((size_t)bank->resources, sizeof(int));
        int *seq = calloc((size_t)bank->customers, sizeof(int));
        if (!r || !seq) {
            free(r); free(seq);
            error("Memory allocation failed");
            return;
        }
        if (!getvec(s, !strcmp(cmd, "request") ? "request" : "release", bank->resources, r, 1000000)) {
            error("Invalid resource vector");
            free(r); free(seq);
            return;
        }
        if (!strcmp(cmd, "request")) {
            int rc = bank_request(bank, c, r, seq);
            const char *st = rc == 1 ? "granted" : rc == 0 ? "unsafe" : rc == -1 ? "exceeds_need" : rc == -2 ? "unavailable" : "invalid";
            printf("{\"status\":\"%s\",\"safe_sequence\":", st);
            if (rc == 1) print_ints(seq, bank->customers); else printf("[]");
            puts("}");
        } else {
            int rel_ok = bank_release(bank, c, r);
            printf("{\"status\":\"%s\"}\n", rel_ok ? "released" : "invalid");
        }
        fflush(stdout);
        free(r);
        free(seq);
        snapshot();

    } else if (!strcmp(cmd, "start_auto")) {
        if (!initialized || !bank) {
            error("Bank is not initialized");
            return;
        }
        int expected = bank->customers;
        int **req = newmat(expected, bank->resources);
        if (!req) {
            error("Memory allocation failed");
            return;
        }
        if (!getmat(s, "requests", expected, bank->resources, req, 1000000)) {
            error("requests must contain one vector per customer");
            freemat(req, expected);
            return;
        }
        pthread_t *th = calloc((size_t)expected, sizeof(pthread_t));
        CustomerArgs *args = calloc((size_t)expected, sizeof(CustomerArgs));
        if (!th || !args) {
            free(th); free(args);
            freemat(req, expected);
            error("Memory allocation failed");
            return;
        }
        int created = 0;
        for (int i = 0; i < expected; i++) {
            args[i] = (CustomerArgs){.bank = bank, .id = i, .request = req[i], .delay_ms = 500};
            if (pthread_create(&th[i], NULL, customer_thread, &args[i]) != 0) {
                break;
            }
            created++;
        }
        for (int i = 0; i < created; i++) {
            pthread_join(th[i], NULL);
        }
        int all_ok = (created == expected);
        printf("{\"event\":\"automatic_complete\",\"threads_expected\":%d,\"threads_created\":%d,\"complete\":%s,\"success\":%s}\n",
               expected, created, all_ok ? "true" : "false", all_ok ? "true" : "false");
        fflush(stdout);
        free(th);
        free(args);
        freemat(req, expected);
        snapshot();

    } else if (!strcmp(cmd, "reset")) {
        if (initialized && bank) {
            bank_destroy(bank);
            free(bank);
            bank = NULL;
            initialized = 0;
        }
        puts("{\"status\":\"ok\",\"message\":\"Bank reset\"}");
        fflush(stdout);

    } else {
        error("Unknown command");
    }
}

int protocol_run(void) {
    while (fgets(line, sizeof(line), stdin)) {
        line[strcspn(line, "\r\n")] = 0;
        if (*line) handle(line);
    }
    if (initialized && bank) {
        bank_destroy(bank);
        free(bank);
        bank = NULL;
        initialized = 0;
    }
    return 0;
}
