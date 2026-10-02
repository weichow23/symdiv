int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static const int STATIC_CONST_TRUE = 1;
static const int STATIC_CONST_FALSE = 0;
void fn_001()
{
    int data;
    data = -1;
    if(STATIC_CONST_TRUE)
    {
        data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    }
    if(STATIC_CONST_TRUE)
    {
        printIntLine(100 % data);
    }
}
