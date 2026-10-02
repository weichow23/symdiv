int rand(void);
void printIntLine(int value);
void printLine(const char *value);
void fn_001()
{
    int data;
    data = -1;
    data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    printIntLine(100 / data);
}
