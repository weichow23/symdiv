int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static void fn_002()
{
    int i,k;
    int data;
    data = -1;
    for(i = 0; i < 1; i++)
    {
        data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    }
    for(k = 0; k < 1; k++)
    {
        if( data != 0 )
        {
            printIntLine(100 / data);
        }
        else
        {
            printLine("message");
        }
    }
}
static void fn_003()
{
    int h,j;
    int data;
    data = -1;
    for(h = 0; h < 1; h++)
    {
        data = 7;
    }
    for(j = 0; j < 1; j++)
    {
        printIntLine(100 / data);
    }
}
void fn_001()
{
    fn_002();
    fn_003();
}
