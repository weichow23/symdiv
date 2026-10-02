/* Minimal interface; RAND32/URAND31 copied exactly from NIST Juliet 1.3. */
#ifndef SYMDIV_JULIET_COMPAT_H
#define SYMDIV_JULIET_COMPAT_H
int rand(void);
void printIntLine(int value);
void printLine(const char *value);
#define URAND31() (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand())
#define RAND32() ((int)(rand() & 1 ? URAND31() : -URAND31() - 1))
#endif
