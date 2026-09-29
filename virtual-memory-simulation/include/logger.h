#ifndef LOGGER_H
#define LOGGER_H

void logger_init(const char *path);
void logger_close(void);
void log_line(const char *fmt, ...);

#endif /* LOGGER_H */
