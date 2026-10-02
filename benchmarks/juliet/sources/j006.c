int rand(void);
void printIntLine(int value);
void printLine(const char *value);
void fn_001()
{
    int i,j;
    int data;
    data = -1;
    for(i = 0; i < 1; i++)
    {
        data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    }
    for(j = 0; j < 1; j++)
    {
        printIntLine(100 / data);
    }
}
