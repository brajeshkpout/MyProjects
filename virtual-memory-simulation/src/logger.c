#include "logger.h"

#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

static FILE *log_fp = NULL;

void logger_init(const char *path) {
    log_fp = fopen(path, "a");
    if (!log_fp) {
        perror("logger_init: fopen");
    }
}

void logger_close(void) {
    if (log_fp) {
        fclose(log_fp);
        log_fp = NULL;
    }
}

static void timestamp(char *buf, size_t n) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    struct tm tmv;
    localtime_r(&tv.tv_sec, &tmv);
    size_t off = strftime(buf, n, "%Y-%m-%d %H:%M:%S", &tmv);
    snprintf(buf + off, n - off, ".%06ld", (long)tv.tv_usec);
}

void log_line(const char *fmt, ...) {
    if (!log_fp) return;

    char ts[64];
    timestamp(ts, sizeof(ts));
    fprintf(log_fp, "[%s] ", ts);

    va_list ap;
    va_start(ap, fmt);
    vfprintf(log_fp, fmt, ap);
    va_end(ap);

    fprintf(log_fp, "\n");
    fflush(log_fp); /* every entry is durable immediately; low volume, so cheap */
}
