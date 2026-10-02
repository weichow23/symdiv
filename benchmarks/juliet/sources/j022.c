int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static const int STATIC_CONST_FIVE = 5;
void fn_001()
{
    int data;
    data = -1;
    if(STATIC_CONST_FIVE==5)
    {
        data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    }
    if(STATIC_CONST_FIVE==5)
    {
        printIntLine(100 / data);
    }
}
